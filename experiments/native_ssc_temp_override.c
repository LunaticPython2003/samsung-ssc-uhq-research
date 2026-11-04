/* Transient, self-restoring Samsung SSC bitrate experiment on user's rooted phone.
 * No files under /system, /apex or vendor are changed; only current process's
 * private copy-on-write rate table. A helper child rolls back even if parent
 * exits unexpectedly. Restrict strictly to table[1] = 584000 -> 886000.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <sys/stat.h>

static volatile sig_atomic_t stop_requested=0;
static void handle_signal(int signum){(void)signum;stop_requested=1;}
static int search_map(pid_t pid, uint64_t *base){
 char path[128],line[520];
 snprintf(path,sizeof(path),"/proc/%d/maps",pid);
 FILE *f=fopen(path,"r");
 if(!f){perror("maps");return -1;}
 int found=0;
 while(fgets(line,sizeof(line),f)){
  unsigned long long a,b,off;char perm[5],name[420]={0};
  if(sscanf(line,"%llx-%llx %4s %llx %*s %*s %419s",&a,&b,perm,&off,name)==5 &&
     off==0 && perm[0]=='r' && perm[1]=='-' &&
     strstr(name,"/apex/com.android.bt/lib64/libbluetooth_jni.so")){
    *base=(uint64_t)a;found++;break;
  }
 }
 fclose(f);
 return found==1?0:-2;
}
static int read_table(int fd, uint64_t addr, uint32_t out[4]){
 ssize_t n=pread(fd,out,16,(off_t)addr);
 return n==16?0:-1;
}
static int restore_if_needed(pid_t pid,uint64_t addr,uint32_t original){
 uint64_t base=0;
 if(search_map(pid,&base)!=0 || addr != base+0x1077b0){
  printf("RESTORE_SKIPPED: process or mapped library changed\n");
  return -1;
 }
 char path[96];snprintf(path,sizeof(path),"/proc/%d/mem",pid);
 int fd=open(path,O_RDWR|O_CLOEXEC);
 if(fd<0){printf("RESTORE_FAILED: cannot open mem errno=%d\n",errno);return -2;}
 uint32_t table[4];int r=read_table(fd,addr,table);
 if(r==0 && table[1]==886000 &&
    table[0]==584000 && table[2]==291000 && table[3]==152000){
   r=pwrite(fd,&original,4,(off_t)(addr+4))==4?0:-3;
   uint32_t after[4];
   if(r==0 && read_table(fd,addr,after)==0 && after[1]==original)
      printf("ROLLBACK_VERIFIED: table[1]=%u\n",after[1]);
   else {r=-4;printf("ROLLBACK_UNVERIFIED errno=%d\n",errno);}
 } else if(r==0 && table[1]==original){
   r=0;printf("ROLLBACK_ALREADY_COMPLETE\n");
 } else {
   r=-5;printf("ROLLBACK_ABORTED: unexpected current table value\n");
 }
 close(fd);fflush(stdout);
 return r;
}
static void sleep_ms(long ms){
 struct timespec ts={.tv_sec=ms/1000,.tv_nsec=(ms%1000)*1000000L};
 while(nanosleep(&ts,&ts)==-1 && errno==EINTR && !stop_requested){}
}
int main(int argc,char**argv){
 setvbuf(stdout,NULL,_IONBF,0);
 if(argc!=3){fprintf(stderr,"usage: %s <bluetooth_pid> <duration_ms 250..5000>\n",argv[0]);return 2;}
 long pl=strtol(argv[1],NULL,10),duration=strtol(argv[2],NULL,10);
 if(pl<=1 || duration<250 || duration>5000) return 2;
 pid_t pid=(pid_t)pl;
 uint64_t base=0;
 if(search_map(pid,&base)!=0){puts("ABORT: exact JNI map not found");return 3;}
 uint64_t addr=base+0x1077b0;
 char path[96];snprintf(path,sizeof(path),"/proc/%d/mem",pid);
 int fd=open(path,O_RDWR|O_CLOEXEC);
 if(fd<0){perror("OPEN_MEM");return 4;}
 uint32_t original[4];
 if(read_table(fd,addr,original)!=0 ||
    original[0]!=584000 || original[1]!=584000 ||
    original[2]!=291000 || original[3]!=152000){
   puts("ABORT: live table does not match exact expected four values");
   close(fd);return 5;
 }
 printf("BEFORE: [%u,%u,%u,%u]\n", original[0],original[1],original[2],original[3]);
 signal(SIGINT,handle_signal);signal(SIGTERM,handle_signal);signal(SIGHUP,handle_signal);
 pid_t guardian=fork();
 if(guardian<0){perror("FORK");close(fd);return 6;}
 if(guardian==0){
   close(fd);
   /* Backup rollback in the event parent is interrupted/killed. */
   sleep_ms(duration+1400);
   int r=restore_if_needed(pid,addr,original[1]);
   _exit(r==0?0:10);
 }
 uint32_t new_rate=886000;
 ssize_t n=pwrite(fd,&new_rate,sizeof(new_rate),(off_t)(addr+4));
 if(n!=4){printf("PATCH_FAILED: bytes=%zd errno=%d\n",n,errno);close(fd);waitpid(guardian,NULL,0);return 7;}
 uint32_t updated[4];
 if(read_table(fd,addr,updated)!=0 ||
    updated[0]!=584000 || updated[1]!=886000 ||
    updated[2]!=291000 || updated[3]!=152000){
   printf("PATCH_READBACK_ERROR\n");
   close(fd);restore_if_needed(pid,addr,original[1]);waitpid(guardian,NULL,0);return 8;
 }
 printf("OVERRIDE_VERIFIED: [%u,%u,%u,%u] TTL_MS=%ld\n",
  updated[0],updated[1],updated[2],updated[3],duration);
 sleep_ms(duration);
 close(fd);
 int outcome=restore_if_needed(pid,addr,original[1]);
 int status=0;waitpid(guardian,&status,0);
 return outcome==0?0:9;
}

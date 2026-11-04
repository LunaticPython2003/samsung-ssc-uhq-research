/* Read-only check of Samsung Bluetooth SSC rate-control table in live memory.
 * NEVER opens /proc/.../mem for writing and never uses ptrace attachment.
 * The address is derived from /proc/PID/maps and a known ELF file offset.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

int main(int argc,char **argv){
 if(argc!=2){fprintf(stderr,"usage: %s bluetooth_pid\n",argv[0]);return 2;}
 long pid=strtol(argv[1],NULL,10);
 if(pid<=0) return 2;
 char path[128];snprintf(path,sizeof(path),"/proc/%ld/maps",pid);
 FILE *fp=fopen(path,"r");
 if(!fp){perror("maps");return 3;}
 char line[512];uint64_t mapstart=0;
 while(fgets(line,sizeof(line),fp)){
   unsigned long long start,end,off;char perm[5],name[384]={0};
   if(sscanf(line,"%llx-%llx %4s %llx %*s %*s %383s",&start,&end,perm,&off,name)==5
     &&strstr(name,"/libbluetooth_jni.so")&&off==0&&perm[0]=='r'){
       mapstart=start;break;
   }
 }
 fclose(fp);
 if(!mapstart){puts("map_not_found");return 4;}
 /* ELF file offset 0x1077B0 is inside first PT_LOAD (p_offset=0, p_vaddr=0). */
 uint64_t target=mapstart+0x1077b0;
 uint32_t vals[4]={0};
 snprintf(path,sizeof(path),"/proc/%ld/mem",pid);
 int fd=open(path,O_RDONLY|O_CLOEXEC);
 if(fd<0){printf("mem_read_denied errno=%d (%s), map=%" PRIx64 ", target=%" PRIx64 "\n",errno,strerror(errno),mapstart,target);return 5;}
 ssize_t n=pread(fd,vals,sizeof(vals),(off_t)target);
 int err=errno;close(fd);
 if(n!=(ssize_t)sizeof(vals)){
   printf("pread_failed bytes=%zd errno=%d (%s) target=%" PRIx64 "\n",n,err,strerror(err),target);return 6;
 }
 printf("READONLY live SSC table at base=%" PRIx64 " target=%" PRIx64 ": [%u,%u,%u,%u]\n",
         mapstart,target,vals[0],vals[1],vals[2],vals[3]);
 return 0;
}

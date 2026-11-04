/* Read-only probe of Samsung SSC mode globals in live com.android.bluetooth.
 * These offsets come from Ghidra's first-segment base 0x00100000 mapping:
 *   DAT_0104aaf8 -> mapped ELF vaddr 0x00f4aaf8.
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
static int read4(int fd,uint64_t addr,uint32_t *v){return pread(fd,v,4,(off_t)addr)==4;}
int main(int argc,char**argv){
 if(argc!=2)return 2;
 int pid=atoi(argv[1]); if(pid<1)return 2;
 char path[100],line[500];snprintf(path,sizeof(path),"/proc/%d/maps",pid);
 FILE *f=fopen(path,"r");if(!f){perror("maps");return 3;}
 uint64_t base=0;unsigned long long s,e,off;char p[8],nm[350];
 while(fgets(line,sizeof(line),f)){
  if(sscanf(line,"%llx-%llx %7s %llx %*s %*s %349s",&s,&e,p,&off,nm)==5
    &&off==0&&strstr(nm,"/libbluetooth_jni.so")){base=s;break;}
 }
 fclose(f);if(!base){puts("mapping_missing");return 4;}
 snprintf(path,sizeof(path),"/proc/%d/mem",pid);
 int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0){perror("mem");return 5;}
 uint32_t target=0,applied=0,rate0=0,rate1=0,rate2=0,rate3=0;
 uint32_t flags=0;
 int good=read4(fd,base+0xf4aaf8,&target) && read4(fd,base+0xf4aafc,&applied)
 && read4(fd,base+0x1077b0,&rate0) && read4(fd,base+0x1077b4,&rate1)
 && read4(fd,base+0x1077b8,&rate2) && read4(fd,base+0x1077bc,&rate3)
 && read4(fd,base+0xf43e80,&flags);
 close(fd);
 if(!good){puts("reads_failed");return 6;}
 printf("SSC_GLOBALS target_bps=%u previous_bps=%u table=[%u,%u,%u,%u] flags_4bytes_le=0x%08x\n",
 target,applied,rate0,rate1,rate2,rate3,flags);
 return 0;
}

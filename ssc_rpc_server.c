/*
 * SSC Android ARM64 encoder backend.
 * One local-only TCP session via adb port forwarding, then exits.
 * No Bluetooth configuration changes. Not an A2DP transport.
 *
 * Wire V1 little endian:
 *  client: "SSC1", u32 rate, u32 channels, u32 depth, u32 bitrate,
 *          u32 frame_samples, u32 version(1)
 *  server: "SSCR", i32 status, i32 context_size
 *  client: u32 pcm_length, signed PCM32 interleaved bytes, repeated;
 *          length=0 closes session.
 *  server: i32 encoded_length (negative=error), then encoded bytes.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <signal.h>
#include <unistd.h>
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#define MAX_OUT 16384U
#define MAX_PCM_BYTES 8192U
#define FRAME_LIMIT 500000U
typedef int (*get_size_fn)(int,int);
typedef void *(*create_fn)(int,int,int,int*);
typedef int (*encode_fn)(void*,int32_t*,int,uint8_t*,int);
typedef void (*destroy_fn)(void*);
static int read_all(int fd,void *ptr,size_t n) {
    uint8_t *p=ptr;
    while(n) {
        ssize_t v=recv(fd,p,n,0);
        if(v<0&&errno==EINTR)continue;
        if(v<=0)return -1;
        p+=v;n-=(size_t)v;
    }
    return 0;
}
static int write_all(int fd,const void *ptr,size_t n) {
    const uint8_t *p=ptr;
    while(n) {
        ssize_t v=send(fd,p,n,MSG_NOSIGNAL);
        if(v<0&&errno==EINTR)continue;
        if(v<=0)return -1;
        p+=v;n-=(size_t)v;
    }
    return 0;
}
static uint32_t rd(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
        ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void wr(uint8_t *p,uint32_t v) {
    p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);
    p[2]=(uint8_t)(v>>16);p[3]=(uint8_t)(v>>24);
}
static int sendcode(int fd,int32_t code) {
    uint8_t tmp[4];wr(tmp,(uint32_t)code);return write_all(fd,tmp,4);
}
static int session(int fd) {
    uint8_t hdr[28],ack[12];
    if(read_all(fd,hdr,sizeof(hdr)))return 10;
    if(memcmp(hdr,"SSC1",4))return 11;
    uint32_t rate=rd(hdr+4),ch=rd(hdr+8),depth=rd(hdr+12),
        bitrate=rd(hdr+16),samples=rd(hdr+20),ver=rd(hdr+24);
    memcpy(ack,"SSCR",4);
    int32_t status=-1,context_bytes=0;
    if(ver!=1||(rate!=44100&&rate!=48000&&rate!=96000)||
        ch!=2||(depth!=16&&depth!=24)||samples<16||samples>1024||
        (bitrate!=88000&&bitrate!=96000&&bitrate!=128000&&
        bitrate!=152000&&bitrate!=192000&&bitrate!=229000&&
        bitrate!=250000&&bitrate!=256000&&bitrate!=291000&&
        bitrate!=308000&&bitrate!=328000&&bitrate!=442000&&
        bitrate!=584000&&bitrate!=886000))goto reject;
    void *lib=dlopen("/system/lib64/libScalable_Encoder.so",RTLD_NOW|RTLD_LOCAL);
    if(!lib) {fprintf(stderr,"dlopen: %s\n",dlerror());status=-2;goto reject;}
    get_size_fn get_size=(get_size_fn)dlsym(lib,"ssc_encoder_get_size");
    create_fn create=(create_fn)dlsym(lib,"ssc_encoder_create");
    encode_fn encode=(encode_fn)dlsym(lib,"ssc_encode");
    destroy_fn destroy=(destroy_fn)dlsym(lib,"ssc_encoder_destroy");
    if(!get_size||!create||!encode||!destroy) {status=-3;goto done_lib;}
    context_bytes=get_size((int)ch,(int)rate);
    if(context_bytes<256||context_bytes>2000000) {status=-4;goto done_lib;}
    int e=-1;
    void *ctx=create((int)rate,(int)ch,(int)depth,&e);
    if(!ctx||e!=0) {
        status=e?e:-5;
        if(ctx)destroy(ctx);
        goto done_lib;
    }
    status=0;
    wr(ack+4,(uint32_t)status);wr(ack+8,(uint32_t)context_bytes);
    if(write_all(fd,ack,sizeof(ack))) {destroy(ctx);goto done_lib;}
    uint8_t *pcm=malloc(MAX_PCM_BYTES),*out=malloc(MAX_OUT+128);
    if(!pcm||!out) {
        sendcode(fd,-6);free(pcm);free(out);destroy(ctx);goto done_lib;
    }
    for(uint32_t f=0;f<FRAME_LIMIT;f++) {
        uint8_t lenbuf[4];
        if(read_all(fd,lenbuf,4))break;
        uint32_t len=rd(lenbuf);
        if(len==0)break;
        if(len!=samples*ch*4||read_all(fd,pcm,len)) {
            sendcode(fd,-7);break;
        }
        memset(out,0xa5,MAX_OUT+128);
        int encoded=encode(ctx,(int32_t*)pcm,(int)samples,out,(int)bitrate);
        int canary=1;
        for(size_t i=MAX_OUT;i<MAX_OUT+128;i++)
            if(out[i]!=0xa5)canary=0;
        if(encoded<4||encoded>(int)MAX_OUT||!canary) {
            fprintf(stderr,"unsafe frame=%u size=%d canary=%d\n",f,encoded,canary);
            sendcode(fd,-8);break;
        }
        size_t last=0;
        for(size_t i=0;i<MAX_OUT;i++)if(out[i]!=0xa5)last=i+1;
        if(last>(size_t)encoded)
            fprintf(stderr,"frame %u modified %zu beyond reported %d\n",
                f,last-(size_t)encoded,encoded);
        if(sendcode(fd,encoded)||write_all(fd,out,(size_t)encoded))break;
    }
    free(pcm);free(out);destroy(ctx);
done_lib:
    dlclose(lib);
    return 0;
reject:
    wr(ack+4,(uint32_t)status);wr(ack+8,(uint32_t)context_bytes);
    write_all(fd,ack,sizeof(ack));
    return 1;
}
int main(int argc,char **argv) {
    int port=23187;
    if(argc>2)return 2;
    if(argc==2) {
        char *end=NULL;long n=strtol(argv[1],&end,10);
        if(*end||n<1025||n>65535)return 2;
        port=(int)n;
    }
    signal(SIGPIPE,SIG_IGN);
    int listener=socket(AF_INET,SOCK_STREAM,0);
    if(listener<0) {perror("socket");return 3;}
    int yes=1;setsockopt(listener,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
    struct sockaddr_in bindaddr={0};
    bindaddr.sin_family=AF_INET;
    bindaddr.sin_port=htons((uint16_t)port);
    bindaddr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if(bind(listener,(struct sockaddr*)&bindaddr,sizeof(bindaddr))<0||
       listen(listener,1)<0) {perror("bind/listen");close(listener);return 3;}
    fprintf(stderr,"ssc-rpc: waiting for one client on 127.0.0.1:%d\n",port);
    int client=accept(listener,NULL,NULL);
    if(client<0) {perror("accept");close(listener);return 4;}
    int no_delay=1;
    setsockopt(client,IPPROTO_TCP,TCP_NODELAY,&no_delay,sizeof(no_delay));
    int rc=session(client);
    close(client);close(listener);
    fprintf(stderr,"ssc-rpc: exit rc=%d\n",rc);
    return rc;
}

/* Enumerate Samsung encoder's exact bitrate identifiers without encoding.
 * Loads the original ARM64 encoder on the user's own Android device.
 * Uses exported get_header_from_bitrate and get_uhq_info_from_bitrate,
 * and never writes Bluetooth settings, pairing data or firmware.
 */
#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned long (*get_marker_t)(int);
typedef void (*get_uhq_t)(int,int*,int*);

static const unsigned int candidates[] = {
    88000, 96000, 128000, 152000, 176000, 192000, 229000, 250000,
    256000, 291000, 308000, 320000, 328000, 384000, 442000, 500000,
    512000, 576000, 584000, 640000, 705600, 768000, 800000, 886000,
    960000, 990000, 1000000, 1024000, 1056000, 1152000, 1200000,
    1280000, 1400000, 1411200, 1536000, 1600000, 1764000, 1800000,
    1920000, 2000000, 2048000, 2116800, 2200000, 2304000, 2400000,
    2500000, 2822400, 3000000, 3528000, 4608000
};
int main(void) {
    void *h=dlopen("/system/lib64/libScalable_Encoder.so", RTLD_NOW|RTLD_LOCAL);
    if(!h){fprintf(stderr,"dlopen: %s\n",dlerror());return 2;}
    get_marker_t marker=(get_marker_t)dlsym(h,"get_header_from_bitrate");
    get_uhq_t flags=(get_uhq_t)dlsym(h,"get_uhq_info_from_bitrate");
    if(!marker||!flags){fprintf(stderr,"missing exported symbols\n");dlclose(h);return 3;}
    puts("requested_bps,header_code,recognized,uhq_flag_a,uhq_flag_b");
    for(size_t i=0;i<sizeof(candidates)/sizeof(*candidates);++i){
        unsigned int bps=candidates[i];
        int a=-777,b=-777;
        unsigned long code=marker((int)bps);
        flags((int)bps,&a,&b);
        printf("%u,0x%02lx,%s,%d,%d\n",bps,code,(code==0xf3?"no":"yes"),a,b);
    }
    dlclose(h);
    return 0;
}

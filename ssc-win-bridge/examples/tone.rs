//! Real Windows -> ADB-forward -> Galaxy SSC encoder example.
//! Start the phone server and ADB forwarding as described in README first.
use ssc_remote_encoder::{Config, EncoderClient, MAX_ENCODED_BYTES};
use std::net::{IpAddr, Ipv4Addr, SocketAddr};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let port: u16 = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "23187".into())
        .parse()?;
    let config = Config {
        sample_rate: 48000,
        channels: 2,
        depth: 24,
        bitrate: 328000,
        samples_per_channel: 864,
    };
    let address = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), port);
    let mut encoder = EncoderClient::connect(address, config)?;
    println!(
        "Windows Rust connected to Galaxy encoder, ctx={} bytes",
        encoder.context_bytes
    );
    let mut out = vec![0u8; MAX_ENCODED_BYTES];
    for frame in 0..3 {
        let mut pcm = vec![0i32; config.pcm_values()];
        for i in 0..config.samples_per_channel as usize {
            let time = (frame * config.samples_per_channel as usize + i) as f64 / 48000.0;
            let val = (time * std::f64::consts::TAU * 440.0).sin();
            let sample = (val * 2_000_000.0) as i32;
            pcm[2 * i] = sample;
            pcm[2 * i + 1] = sample;
        }
        let len = encoder.encode_right_aligned_i32(&pcm, &mut out)?;
        println!(
            "frame={frame} bytes={len} prefix={:02x?}",
            &out[..len.min(12)]
        );
        if out[0] != 0xff || !matches!(out[1], 0xee | 0xe0) {
            return Err(format!("unexpected SSC probe sync bytes: {:02x?}", &out[..2]).into());
        }
    }
    Ok(())
}

//! Probe the exact encoder mode observed during live Buds4 Pro playback.
//! This is research-only: it does not send audio over Bluetooth.
//!
//! Live observation 2026-11-03:
//! 96 kHz, stereo 24-bit, selected 584000 bps, reported peer MTU 1005.
//! The proprietary media header remains unknown, so the printed MTU fit
//! is explicitly a size check, NOT a validated send packet.
use ssc_remote_encoder::{
    Config, EncoderClient, MAX_ENCODED_BYTES,
    transport::{MediaLimits, SSC_PCM_FRAMES_PER_CODEC_FRAME},
};
use std::net::{IpAddr, Ipv4Addr, SocketAddr};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let port: u16 = std::env::args().nth(1).unwrap_or("23187".into()).parse()?;
    let cfg = Config {
        sample_rate: 96000,
        channels: 2,
        depth: 24,
        bitrate: 584000,
        samples_per_channel: SSC_PCM_FRAMES_PER_CODEC_FRAME as u32,
    };
    let address = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), port);
    let mut encoder = EncoderClient::connect(address, cfg)?;
    let limits = MediaLimits {
        transport_mtu: 1005,
        media_header_bytes: 0, // lower bound; actual Samsung header unconfirmed
        uses_rtp: true,
    };
    println!(
        "Live-mode local probe: {} Hz, {}-ch, {}-bit, {} bps; peer MTU {}; encoder ctx {} bytes",
        cfg.sample_rate,
        cfg.channels,
        cfg.depth,
        cfg.bitrate,
        limits.transport_mtu,
        encoder.context_bytes
    );
    let mut output = vec![0u8; MAX_ENCODED_BYTES];
    for frame in 0..8 {
        let mut pcm = vec![0i32; cfg.pcm_values()];
        for i in 0..cfg.samples_per_channel as usize {
            let t =
                (frame * cfg.samples_per_channel as usize + i) as f64 / f64::from(cfg.sample_rate);
            let sample = ((t * std::f64::consts::TAU * 440.0).sin() * 2_000_000.0) as i32;
            pcm[2 * i] = sample;
            pcm[2 * i + 1] = sample;
        }
        let bytes = encoder.encode_right_aligned_i32(&pcm, &mut output)?;
        let cap = limits.inspect_frame(bytes)?;
        println!(
            "frame {frame}: {} encoded bytes; conservative payload <= {} bytes; overhead >= {}; size-fit {}",
            bytes,
            cap.effective_payload_bytes,
            limits.overhead(),
            cap.estimated_encoded_frame_fit
        );
        if !cap.estimated_encoded_frame_fit {
            return Err(format!(
                "frame {frame} too large for reported MTU even without a proprietary media header"
            )
            .into());
        }
    }
    println!("Probe complete; no radio packets transmitted.");
    Ok(())
}

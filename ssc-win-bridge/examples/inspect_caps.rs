//! Inspect Samsung SSC AVDTP codec capability bytes without connecting earbuds.
//! Examples:
//!   cargo run --example inspect_caps -- "09 00 ff 75 00 00 00 03 01 30"
//!   cargo run --example inspect_caps -- "75 00 00 00 03 01 30"
//!
//! 10-byte full CIE OR 7-byte BTstack media codec info, hex with optional spaces.
use ssc_remote_encoder::ssc_a2dp::{BTSTACK_INFO_LEN, CODEC_ID, SscInfo, VENDOR_ID, WIRE_CIE_LEN};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        return Err("provide 7 or 10 bytes as hex".into());
    }
    let hex = args
        .join("")
        .chars()
        .filter(|c| c.is_ascii_hexdigit())
        .collect::<String>();
    if hex.len() % 2 != 0 {
        return Err("odd number of hex digits".into());
    }
    let bytes: Vec<u8> = (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16))
        .collect::<Result<_, _>>()?;
    let info = match bytes.len() {
        WIRE_CIE_LEN => SscInfo::parse_full_cie(&bytes),
        BTSTACK_INFO_LEN => SscInfo::parse_btstack(&bytes),
        _ => return Err("expected 7-byte BTstack info or 10-byte full CIE".into()),
    }?;
    println!("Samsung SSC parser candidate: vendor=0x{VENDOR_ID:08x}, codec=0x{CODEC_ID:04x}");
    println!(
        "Rate flags: {:02x}, rates: {:?}",
        info.flags & 0xf0,
        info.rates()
    );
    println!("Feature bits: 0x{:x}", info.features());
    println!("  UHQ2 flag: {}", info.is_uhq2());
    println!("  bitrate limiter active: {}", info.bitrate_limited());
    if let Ok(mode) = info.stack_mode_code() {
        println!("  Samsung stack mode code: 0x{mode:03x}");
    } else {
        println!("  stack mode requires a single selected sample rate");
    }
    println!("  remaining low-bit meanings still unverified");
    println!("Software-encoder-compatible rates: {:?}", {
        info.rates()
            .into_iter()
            .filter(|r| *r != 32000)
            .collect::<Vec<_>>()
    });
    println!("BTstack info: {:02x?}", info.btstack_info());
    println!("Complete codec element: {:02x?}", info.full_cie());
    println!(
        "Note: this validates parsed bytes only; it does not demonstrate device compatibility."
    );
    Ok(())
}

//! AVDTP SSC vendor-codec parsing reconstructed from Samsung's
//! /apex/com.android.bt/lib64/libbluetooth_jni.so (Galaxy Z Fold7, Nov 2026).
//!
//! This is NOT an interoperable encoder on its own and does NOT advertise a
//! tested Bluetooth SEP. Codec-specific lower nibble semantics are incomplete.
//! Only parse capabilities; configuration requires explicit caller-selected
//! opaque feature flags and a verified peer.
//!
//! Source function: A2DP_ParseInfoSsc, A2DP_VendorGetTrackSampleRateSsc.
//! Sample-rate byte flags (offset 9 in 10-byte full CIE):
//!   0x10=48k, 0x20=44.1k, 0x40=32k, 0x80=96k.
//! The ARM64 software encoder itself supports only 44.1k, 48k, 96k.

use std::fmt;

pub const VENDOR_ID: u32 = 0x0000_0075;
pub const CODEC_ID: u16 = 0x0103; // enforced by A2DP_ParseInfoSsc
/// Distinct vendor codec ID in the static InitCodecConfigSsc blob.
/// Its role is not established; do not transmit it as SSC without a trace.
pub const STATIC_INIT_CODEC_ID_UNVERIFIED: u16 = 0x0e03;
/// A2DP_VendorUsesRtpHeaderSsc returns true (1) on the analyzed build.
pub const USES_RTP_HEADER: bool = true;
pub const VENDOR_CODEC_TYPE: u8 = 0xFF;
pub const MEDIA_AUDIO: u8 = 0x00;
pub const WIRE_CIE_LEN: usize = 10;
pub const BTSTACK_INFO_LEN: usize = 7;
pub const SAMPLING_48K: u8 = 0x10;
pub const SAMPLING_44K1: u8 = 0x20;
pub const SAMPLING_32K: u8 = 0x40;
pub const SAMPLING_96K: u8 = 0x80;
pub const SAMPLING_MASK: u8 = 0xF0;
pub const FEATURE_MASK: u8 = 0x0F;
/// From A2DP_VendorGetSscType: bit 1 selects UHQ2 (mode code 0x400).
pub const FEATURE_UHQ2: u8 = 0x02;
/// From A2DP_VendorGetTrackBitrateLimitationSsc: bitrate limitation is
/// true when this bit is CLEAR (inverse/negative-polarity flag).
pub const FEATURE_UNRESTRICTED_BITRATE: u8 = 0x08;
/// Bit 2 influences the legacy mode code, without proving its feature name.
pub const FEATURE_LEGACY_MODE_SELECT: u8 = 0x04;

/// Recovered lookup tables from Samsung's SscBitrateByBusyLevel function.
/// The index is a busy/quality level clamped to 3.
pub const UHQ2_BITRATES: [u32; 4] = [584000, 584000, 291000, 152000];
pub const SSC_96K_LEGACY_BITRATES: [u32; 4] = [328000, 328000, 328000, 328000];
pub const SSC_STANDARD_BITRATES: [u32; 4] = [192000, 192000, 128000, 88000];
pub const SSC_LIMITED_BITRATES: [u32; 4] = [128000, 128000, 128000, 88000];

/// The AIDL SscBitrateByBusyLevel selection, based on the inspected Galaxy
/// Z Fold7 Bluetooth stack. `rate_limited` applies to standard modes; UHQ2
/// and 0x200 bypass this flag in the decompiled branch. It returns a target
/// bitrate, not measured on-air RF throughput.
pub fn bitrate_by_busy_level(mode: u16, level: u16, rate_limited: bool) -> u32 {
    let index = usize::from(level.min(3));
    match mode {
        0x400 => UHQ2_BITRATES[index],
        0x200 => SSC_96K_LEGACY_BITRATES[index],
        _ if rate_limited => SSC_LIMITED_BITRATES[index],
        _ => SSC_STANDARD_BITRATES[index],
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SscCodecError {
    UnexpectedLength { got: usize, expected: usize },
    BadPrefix,
    WrongVendor { vendor: u32, codec: u16 },
    NoSampleRates,
    UnsupportedRate(u32),
    RateNotSupported(u32),
    UnsupportedFeatures(u8),
    AmbiguousConfiguration,
}
impl fmt::Display for SscCodecError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for SscCodecError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SscInfo {
    /// One byte of codec-specific configuration (rate nibble | feature nibble).
    pub flags: u8,
}
impl SscInfo {
    pub fn rates(self) -> Vec<u32> {
        let mut v = Vec::new();
        if self.flags & SAMPLING_44K1 != 0 {
            v.push(44100);
        }
        if self.flags & SAMPLING_48K != 0 {
            v.push(48000);
        }
        if self.flags & SAMPLING_96K != 0 {
            v.push(96000);
        }
        if self.flags & SAMPLING_32K != 0 {
            v.push(32000);
        }
        v
    }
    pub fn features(self) -> u8 {
        self.flags & FEATURE_MASK
    }
    /// True when the parsed SSC field selects Samsung's UHQ2 mode (0x400).
    pub fn is_uhq2(self) -> bool {
        self.features() & FEATURE_UHQ2 != 0
    }
    /// Returns the boolean used by Samsung's bitrate limitation getter.
    pub fn bitrate_limited(self) -> bool {
        self.features() & FEATURE_UNRESTRICTED_BITRATE == 0
    }
    /// Reproduces the A2DP_VendorGetSscType branch ordering. Only valid
    /// after selecting a single sample rate, not on multi-rate capabilities.
    pub fn stack_mode_code(self) -> Result<u16, SscCodecError> {
        let sample_rate = self.require_single_rate()?;
        Ok(if self.is_uhq2() {
            0x400
        } else if sample_rate == 96000 {
            0x200
        } else if self.features() & FEATURE_LEGACY_MODE_SELECT != 0 {
            0x100
        } else {
            0x080
        })
    }
    /// Return the vendor codec information normally carried by BTstack:
    /// 32-bit vendor LE, 16-bit codec LE, one byte of SSC flags.
    pub fn btstack_info(self) -> [u8; BTSTACK_INFO_LEN] {
        let mut bytes = [0; BTSTACK_INFO_LEN];
        bytes[..4].copy_from_slice(&VENDOR_ID.to_le_bytes());
        bytes[4..6].copy_from_slice(&CODEC_ID.to_le_bytes());
        bytes[6] = self.flags;
        bytes
    }
    /// Complete 10-byte A2DP codec information element used by Samsung's parser.
    pub fn full_cie(self) -> [u8; WIRE_CIE_LEN] {
        let mut bytes = [0; WIRE_CIE_LEN];
        bytes[0] = 9; // length of the remaining bytes
        bytes[1] = MEDIA_AUDIO << 4;
        bytes[2] = VENDOR_CODEC_TYPE;
        bytes[3..].copy_from_slice(&self.btstack_info());
        bytes
    }
    pub fn parse_btstack(info: &[u8]) -> Result<Self, SscCodecError> {
        if info.len() != BTSTACK_INFO_LEN {
            return Err(SscCodecError::UnexpectedLength {
                got: info.len(),
                expected: BTSTACK_INFO_LEN,
            });
        }
        let vendor = u32::from_le_bytes(info[..4].try_into().unwrap());
        let codec = u16::from_le_bytes(info[4..6].try_into().unwrap());
        if vendor != VENDOR_ID || codec != CODEC_ID {
            return Err(SscCodecError::WrongVendor { vendor, codec });
        }
        let flags = info[6];
        if flags & SAMPLING_MASK == 0 {
            return Err(SscCodecError::NoSampleRates);
        }
        Ok(Self { flags })
    }
    pub fn parse_full_cie(cie: &[u8]) -> Result<Self, SscCodecError> {
        if cie.len() != WIRE_CIE_LEN {
            return Err(SscCodecError::UnexpectedLength {
                got: cie.len(),
                expected: WIRE_CIE_LEN,
            });
        }
        if cie[0] != 9 || cie[1] >> 4 != MEDIA_AUDIO || cie[2] != VENDOR_CODEC_TYPE {
            return Err(SscCodecError::BadPrefix);
        }
        Self::parse_btstack(&cie[3..])
    }
    /// Build a *candidate* configuration from peer advertised flags. The
    /// opaque lower-bit feature mask must be selected by a caller with an
    /// independently verified sink configuration. Never guess feature flags.
    pub fn select_explicit(self, hz: u32, selected_features: u8) -> Result<Self, SscCodecError> {
        let rate = match hz {
            44100 => SAMPLING_44K1,
            48000 => SAMPLING_48K,
            96000 => SAMPLING_96K,
            _ => return Err(SscCodecError::UnsupportedRate(hz)),
        };
        if self.flags & rate == 0 {
            return Err(SscCodecError::RateNotSupported(hz));
        }
        if selected_features & !FEATURE_MASK != 0 || selected_features & !self.features() != 0 {
            return Err(SscCodecError::UnsupportedFeatures(selected_features));
        }
        Ok(Self {
            flags: rate | selected_features,
        })
    }
    pub fn require_single_rate(self) -> Result<u32, SscCodecError> {
        let bits = self.flags & SAMPLING_MASK;
        if bits.count_ones() != 1 {
            return Err(SscCodecError::AmbiguousConfiguration);
        }
        match bits {
            SAMPLING_44K1 => Ok(44100),
            SAMPLING_48K => Ok(48000),
            SAMPLING_96K => Ok(96000),
            _ => Err(SscCodecError::UnsupportedRate(32000)),
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bitrate_tables_match_live_level_change() {
        assert_eq!(bitrate_by_busy_level(0x400, 2, false), 291000);
        assert_eq!(bitrate_by_busy_level(0x400, 1, false), 584000);
        assert_eq!(bitrate_by_busy_level(0x400, 3, false), 152000);
        assert_eq!(bitrate_by_busy_level(0x400, 100, true), 152000);
        for level in 0..=3 {
            assert_eq!(bitrate_by_busy_level(0x200, level, false), 328000);
        }
        assert_eq!(bitrate_by_busy_level(0x100, 0, false), 192000);
        assert_eq!(bitrate_by_busy_level(0x100, 0, true), 128000);
        assert_eq!(bitrate_by_busy_level(0x100, 3, true), 88000);
    }

    #[test]
    fn parsed_mode_and_bitrate_flags_match_samsung_stack() {
        // 0x8A is a minimal *candidate* for the observed UHQ2/96k/
        // unrestricted mode; it is NOT a recorded on-air configuration.
        let candidate = SscInfo { flags: 0x8A };
        assert_eq!(candidate.require_single_rate().unwrap(), 96000);
        assert_eq!(candidate.stack_mode_code().unwrap(), 0x400);
        assert!(candidate.is_uhq2());
        assert!(!candidate.bitrate_limited());
        assert_eq!(SscInfo { flags: 0x80 }.stack_mode_code().unwrap(), 0x200);
        assert_eq!(SscInfo { flags: 0x24 }.stack_mode_code().unwrap(), 0x100);
        assert_eq!(SscInfo { flags: 0x20 }.stack_mode_code().unwrap(), 0x080);
        assert!(SscInfo { flags: 0xF2 }.stack_mode_code().is_err());
    }

    #[test]
    fn parse_minimal_codec_info() {
        let info = [0x75, 0, 0, 0, 0x03, 0x01, 0x30];
        let s = SscInfo::parse_btstack(&info).unwrap();
        assert_eq!(s.rates(), vec![44100, 48000]);
        assert_eq!(s.full_cie(), [9, 0, 0xff, 0x75, 0, 0, 0, 3, 1, 0x30]);
        assert_eq!(SscInfo::parse_full_cie(&s.full_cie()).unwrap(), s);
    }
    #[test]
    fn reject_wrong_vendor_or_invalid_cie() {
        assert!(matches!(
            SscInfo::parse_btstack(&[0, 0, 0, 0, 3, 1, 0x10]),
            Err(SscCodecError::WrongVendor { .. })
        ));
        assert!(matches!(
            SscInfo::parse_btstack(&[0x75, 0, 0, 0, 3, 1, 0]),
            Err(SscCodecError::NoSampleRates)
        ));
        let mut wrong = [9, 0, 0xff, 0x75, 0, 0, 0, 3, 1, 0x10];
        wrong[2] = 0;
        assert_eq!(
            SscInfo::parse_full_cie(&wrong),
            Err(SscCodecError::BadPrefix)
        );
    }
    #[test]
    fn refuse_guessing_unsupported_peer_flags() {
        let peer = SscInfo { flags: 0x92 };
        assert_eq!(peer.select_explicit(96000, 2).unwrap().flags, 0x82);
        assert_eq!(peer.select_explicit(48000, 2).unwrap().flags, 0x12);
        assert!(matches!(
            peer.select_explicit(48000, 4),
            Err(SscCodecError::UnsupportedFeatures(4))
        ));
        assert!(matches!(
            peer.select_explicit(44100, 2),
            Err(SscCodecError::RateNotSupported(44100))
        ));
        assert!(matches!(
            peer.select_explicit(32000, 2),
            Err(SscCodecError::UnsupportedRate(32000))
        ));
        assert!(matches!(
            peer.require_single_rate(),
            Err(SscCodecError::AmbiguousConfiguration)
        ));
        assert_eq!(
            SscInfo { flags: 0x80 }.require_single_rate().unwrap(),
            96000
        );
    }
}

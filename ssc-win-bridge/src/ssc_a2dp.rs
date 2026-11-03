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

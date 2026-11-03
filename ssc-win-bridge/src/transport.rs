//! Conservative SSC over-A2DP packet-size preflight.
//! No Bluetooth transmission, and no guessed Samsung codec media header.
//! A2DPWB's a2dp_send_media_payload_rtp adds RTP itself.
//! The negotiated transport MTU includes the 12-byte fixed RTP header.

use std::fmt;

pub const RTP_V2_FIXED_HEADER_LEN: usize = 12;
/// Verified Samsung encoder callsite sample count; 864 PCM samples per channel.
pub const SSC_PCM_FRAMES_PER_CODEC_FRAME: usize = 864;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct MediaLimits {
    pub transport_mtu: usize,
    /// Caller must determine header size from a verified target device trace.
    pub media_header_bytes: usize,
    pub uses_rtp: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PacketCapacity {
    pub encoded_frame_bytes: usize,
    pub transport_mtu: usize,
    pub effective_payload_bytes: usize,
    pub estimated_encoded_frame_fit: bool,
    pub required_mtu_for_one_frame: usize,
    pub overflow_bytes: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PacketError {
    ZeroMtu,
    MtuTooSmall {
        mtu: usize,
        overhead: usize,
    },
    EmptyFrame,
    FrameTooLarge {
        encoded_bytes: usize,
        payload_budget: usize,
    },
}

impl fmt::Display for PacketError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ZeroMtu => f.write_str("MTU must be nonzero"),
            Self::MtuTooSmall { mtu, overhead } => {
                write!(f, "transport MTU {mtu} smaller than headers {overhead}")
            }
            Self::EmptyFrame => f.write_str("empty encoded frame"),
            Self::FrameTooLarge {
                encoded_bytes,
                payload_budget,
            } => write!(
                f,
                "encoded frame {encoded_bytes} bytes exceeds single-packet payload {payload_budget} bytes; verified codec fragmentation is required"
            ),
        }
    }
}
impl std::error::Error for PacketError {}

impl MediaLimits {
    pub fn overhead(self) -> usize {
        self.media_header_bytes
            + if self.uses_rtp {
                RTP_V2_FIXED_HEADER_LEN
            } else {
                0
            }
    }

    pub fn payload_bytes(self) -> Result<usize, PacketError> {
        if self.transport_mtu == 0 {
            return Err(PacketError::ZeroMtu);
        }
        let overhead = self.overhead();
        if self.transport_mtu <= overhead {
            return Err(PacketError::MtuTooSmall {
                mtu: self.transport_mtu,
                overhead,
            });
        }
        Ok(self.transport_mtu - overhead)
    }

    /// Size check only. A fit does NOT establish peer compatibility.
    pub fn inspect_frame(self, encoded_bytes: usize) -> Result<PacketCapacity, PacketError> {
        if encoded_bytes == 0 {
            return Err(PacketError::EmptyFrame);
        }
        let budget = self.payload_bytes()?;
        Ok(PacketCapacity {
            encoded_frame_bytes: encoded_bytes,
            transport_mtu: self.transport_mtu,
            effective_payload_bytes: budget,
            estimated_encoded_frame_fit: encoded_bytes <= budget,
            required_mtu_for_one_frame: encoded_bytes + self.overhead(),
            overflow_bytes: encoded_bytes.saturating_sub(budget),
        })
    }

    pub fn require_complete_frame(self, encoded_bytes: usize) -> Result<usize, PacketError> {
        let cap = self.inspect_frame(encoded_bytes)?;
        if !cap.estimated_encoded_frame_fit {
            return Err(PacketError::FrameTooLarge {
                encoded_bytes,
                payload_budget: cap.effective_payload_bytes,
            });
        }
        Ok(encoded_bytes)
    }
}

/// Offline timestamp cursor, not an assertion about proprietary packet policy.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RtpCursor {
    pub sequence: u16,
    pub timestamp: u32,
    pub samples_per_encoded_frame: u32,
}
impl RtpCursor {
    pub fn advance_frame(&mut self) {
        self.sequence = self.sequence.wrapping_add(1);
        self.timestamp = self.timestamp.wrapping_add(self.samples_per_encoded_frame);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_mtu_cannot_fit_observed_806_byte_frame() {
        let limits = MediaLimits {
            transport_mtu: 679,
            media_header_bytes: 0,
            uses_rtp: true,
        };
        let cap = limits.inspect_frame(806).unwrap();
        assert_eq!(cap.effective_payload_bytes, 667);
        assert_eq!(cap.required_mtu_for_one_frame, 818);
        assert_eq!(cap.overflow_bytes, 139);
        assert!(!cap.estimated_encoded_frame_fit);
        assert_eq!(
            limits.require_complete_frame(806),
            Err(PacketError::FrameTooLarge {
                encoded_bytes: 806,
                payload_budget: 667
            })
        );
    }

    #[test]
    fn mtu_large_enough_for_one_frame() {
        let limits = MediaLimits {
            transport_mtu: 1008,
            media_header_bytes: 1,
            uses_rtp: true,
        };
        assert_eq!(limits.require_complete_frame(806).unwrap(), 806);
        assert_eq!(
            limits.inspect_frame(806).unwrap().effective_payload_bytes,
            995
        );
        assert!(
            !limits
                .inspect_frame(1000)
                .unwrap()
                .estimated_encoded_frame_fit
        );
    }

    #[test]
    fn empty_and_invalid_mtu() {
        let limits = MediaLimits {
            transport_mtu: 12,
            media_header_bytes: 0,
            uses_rtp: true,
        };
        assert!(matches!(
            limits.payload_bytes(),
            Err(PacketError::MtuTooSmall { .. })
        ));
        let sane = MediaLimits {
            transport_mtu: 679,
            media_header_bytes: 0,
            uses_rtp: true,
        };
        assert_eq!(sane.inspect_frame(0), Err(PacketError::EmptyFrame));
    }

    #[test]
    fn live_buds4_pro_96khz_mtu_preflight() {
        // Observed 2026-11-03: Samsung reports a peer MTU of 1005 bytes.
        // ARM64 encoder returned 330 bytes at 291000 bps and 660 at 584000.
        // This only checks size: the proprietary media header is unknown.
        let mtu = MediaLimits {
            transport_mtu: 1005,
            media_header_bytes: 0,
            uses_rtp: true,
        };
        assert_eq!(mtu.payload_bytes().unwrap(), 993);
        assert_eq!(mtu.require_complete_frame(330).unwrap(), 330);
        assert_eq!(mtu.require_complete_frame(660).unwrap(), 660);
        assert!(matches!(
            mtu.require_complete_frame(1000),
            Err(PacketError::FrameTooLarge { .. })
        ));
    }

    #[test]
    fn sequence_and_timestamp_rollover() {
        let mut cursor = RtpCursor {
            sequence: u16::MAX,
            timestamp: u32::MAX - 100,
            samples_per_encoded_frame: 864,
        };
        cursor.advance_frame();
        assert_eq!(cursor.sequence, 0);
        assert_eq!(cursor.timestamp, 763);
    }
}

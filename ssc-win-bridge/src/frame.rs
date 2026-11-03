//! Recovered signatures for frames output by Samsung's SSC ARM64 encoder.
//!
//! These are *codec-frame* headers, NOT RTP or A2DP media payload headers.
//! Observed in 2026-11-03 local synthetic test frames, not verified against
//! over-the-air captures. Never infer wireless packet boundaries from them.

use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameFamily {
    /// Header bytes begin FF EE, a 4-bit sequence counter in byte 2 high nibble.
    ShortCounter,
    /// Header begins FF E0..EF, an 8-bit counter in byte1 low/byte2 high nibble.
    ExtendedCounter,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FrameHeader {
    pub family: FrameFamily,
    pub sequence: u8,
    pub sequence_modulus: u16,
    pub first_four: [u8; 4],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FrameHeaderError {
    TooShort,
    UnknownSync([u8; 2]),
    FamilyMismatch,
    SequenceGap { expected: u8, got: u8 },
}
impl fmt::Display for FrameHeaderError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for FrameHeaderError {}

pub fn parse_frame_header(bytes: &[u8]) -> Result<FrameHeader, FrameHeaderError> {
    if bytes.len() < 4 {
        return Err(FrameHeaderError::TooShort);
    }
    let prefix = [bytes[0], bytes[1]];
    let family = if prefix == [0xff, 0xee] {
        FrameFamily::ShortCounter
    } else if bytes[0] == 0xff && (bytes[1] & 0xf0) == 0xe0 {
        FrameFamily::ExtendedCounter
    } else {
        return Err(FrameHeaderError::UnknownSync(prefix));
    };
    let (sequence, sequence_modulus) = match family {
        FrameFamily::ShortCounter => (bytes[2] >> 4, 16),
        FrameFamily::ExtendedCounter => (((bytes[1] & 0x0f) << 4) | (bytes[2] >> 4), 256),
    };
    Ok(FrameHeader {
        family,
        sequence,
        sequence_modulus,
        first_four: [bytes[0], bytes[1], bytes[2], bytes[3]],
    })
}
pub fn check_next_frame(prev: FrameHeader, next: FrameHeader) -> Result<(), FrameHeaderError> {
    if prev.family != next.family {
        return Err(FrameHeaderError::FamilyMismatch);
    }
    let expected = ((u16::from(prev.sequence) + 1) % prev.sequence_modulus) as u8;
    if next.sequence != expected {
        return Err(FrameHeaderError::SequenceGap {
            expected,
            got: next.sequence,
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extended_counter_at_96khz_584kbps() {
        let a = parse_frame_header(&[0xff, 0xe0, 0x0d, 0x03]).unwrap();
        let b = parse_frame_header(&[0xff, 0xe0, 0x1d, 0x03]).unwrap();
        let c = parse_frame_header(&[0xff, 0xe1, 0x0d, 0x03]).unwrap();
        let d = parse_frame_header(&[0xff, 0xe1, 0x1d, 0x03]).unwrap();
        assert_eq!(a.family, FrameFamily::ExtendedCounter);
        assert_eq!(a.sequence, 0);
        assert_eq!(b.sequence, 1);
        assert_eq!(c.sequence, 16);
        assert_eq!(d.sequence, 17);
        check_next_frame(a, b).unwrap();
        check_next_frame(c, d).unwrap();
    }

    #[test]
    fn short_counter_at_48khz_328kbps_wraps() {
        let a = parse_frame_header(&[0xff, 0xee, 0xf1, 0xf5]).unwrap();
        let b = parse_frame_header(&[0xff, 0xee, 0x01, 0xf5]).unwrap();
        assert_eq!(a.family, FrameFamily::ShortCounter);
        assert_eq!(a.sequence, 15);
        assert_eq!(b.sequence, 0);
        check_next_frame(a, b).unwrap();
    }

    #[test]
    fn detects_unknown_header_or_sequence_gap() {
        assert_eq!(
            parse_frame_header(&[0xff, 0xe0]),
            Err(FrameHeaderError::TooShort)
        );
        assert_eq!(
            parse_frame_header(&[0xff, 0xa0, 0, 0]),
            Err(FrameHeaderError::UnknownSync([0xff, 0xa0]))
        );
        let a = parse_frame_header(&[0xff, 0xe0, 0x0d, 3]).unwrap();
        let b = parse_frame_header(&[0xff, 0xe0, 0x2d, 3]).unwrap();
        assert_eq!(
            check_next_frame(a, b),
            Err(FrameHeaderError::SequenceGap {
                expected: 1,
                got: 2
            })
        );
    }
}

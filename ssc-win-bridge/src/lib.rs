//! Windows-native transport wrapper around an Android-hosted SSC encoder.
//!
//! This Rust library runs on x64 Windows. The SSC algorithm itself still runs
//! inside the unmodified ARM64 Samsung .so on the connected Android device.
//! Encoded bytes have NOT been validated as a Bluetooth A2DP payload.
//!
//! Usage: run ssc_rpc_server via ADB forwarding, then call EncoderClient::connect.
//! Designed to become the codec backend for the A2DP Windows Bridge project.

pub mod frame;
pub mod ssc_a2dp;
pub mod transport;

use std::fmt;
use std::io::{self, Read, Write};
use std::net::{Shutdown, SocketAddr, TcpStream};
use std::time::Duration;

pub const PROTOCOL_VERSION: u32 = 1;
pub const MAX_ENCODED_BYTES: usize = 16384;

#[derive(Debug, Clone, Copy)]
pub struct Config {
    pub sample_rate: u32,
    pub channels: u32,
    pub depth: u32,
    pub bitrate: u32,
    pub samples_per_channel: u32,
}

impl Config {
    pub fn validate(&self) -> Result<(), SscError> {
        if !matches!(self.sample_rate, 44100 | 48000 | 96000)
            || self.channels != 2
            || !matches!(self.depth, 16 | 24)
            || !(16..=1024).contains(&self.samples_per_channel)
            || !matches!(
                self.bitrate,
                88000
                    | 96000
                    | 128000
                    | 152000
                    | 192000
                    | 229000
                    | 250000
                    | 256000
                    | 291000
                    | 308000
                    | 328000
                    | 442000
                    | 584000
                    | 886000
            )
        {
            return Err(SscError::InvalidConfig);
        }
        Ok(())
    }

    pub fn pcm_values(&self) -> usize {
        self.samples_per_channel as usize * self.channels as usize
    }
}

#[derive(Debug)]
pub enum SscError {
    Io(io::Error),
    InvalidConfig,
    InputLength { expected: usize, actual: usize },
    OutputTooSmall { provided: usize, needed: usize },
    Protocol(&'static str),
    Backend(i32),
}

impl fmt::Display for SscError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(e) => write!(f, "I/O: {e}"),
            Self::InvalidConfig => f.write_str("unsupported SSC configuration"),
            Self::InputLength { expected, actual } => {
                write!(f, "PCM needs {expected} samples, received {actual}")
            }
            Self::OutputTooSmall { provided, needed } => {
                write!(f, "SSC output needs {needed} bytes, has {provided}")
            }
            Self::Protocol(s) => write!(f, "malformed SSC RPC: {s}"),
            Self::Backend(code) => write!(f, "Samsung encoder backend error {code}"),
        }
    }
}
impl std::error::Error for SscError {}
impl From<io::Error> for SscError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

pub struct EncoderClient {
    stream: TcpStream,
    config: Config,
    pcm_scratch: Vec<u8>,
    encoded_scratch: Vec<u8>,
    pub context_bytes: i32,
}

impl EncoderClient {
    pub fn connect(addr: SocketAddr, config: Config) -> Result<Self, SscError> {
        config.validate()?;
        let mut stream = TcpStream::connect_timeout(&addr, Duration::from_secs(5))?;
        stream.set_nodelay(true)?;
        stream.set_read_timeout(Some(Duration::from_secs(2)))?;
        stream.set_write_timeout(Some(Duration::from_secs(2)))?;

        let mut hello = [0u8; 28];
        hello[..4].copy_from_slice(b"SSC1");
        for (i, word) in [
            config.sample_rate,
            config.channels,
            config.depth,
            config.bitrate,
            config.samples_per_channel,
            PROTOCOL_VERSION,
        ]
        .iter()
        .enumerate()
        {
            hello[4 + i * 4..8 + i * 4].copy_from_slice(&word.to_le_bytes());
        }
        stream.write_all(&hello)?;
        let mut ack = [0u8; 12];
        stream.read_exact(&mut ack)?;
        if &ack[..4] != b"SSCR" {
            return Err(SscError::Protocol("invalid server acknowledgement"));
        }
        let status = i32::from_le_bytes(ack[4..8].try_into().unwrap());
        if status != 0 {
            return Err(SscError::Backend(status));
        }
        let context_bytes = i32::from_le_bytes(ack[8..12].try_into().unwrap());
        if !(256..=2_000_000).contains(&context_bytes) {
            return Err(SscError::Protocol("implausible encoder context size"));
        }
        Ok(Self {
            stream,
            config,
            pcm_scratch: vec![0u8; config.pcm_values() * 4],
            encoded_scratch: vec![0u8; MAX_ENCODED_BYTES],
            context_bytes,
        })
    }

    pub fn config(&self) -> Config {
        self.config
    }

    /// PCM input is 32-bit signed but carries 24-bit data in the lower bits:
    /// this is the on-phone encoder representation used by the validated probe.
    pub fn encode_right_aligned_i32(
        &mut self,
        pcm: &[i32],
        output: &mut [u8],
    ) -> Result<usize, SscError> {
        self.encode_impl(pcm, output, false)
    }

    /// A2DPWB's PcmFormat::I32 is MSB-aligned. Convert its top 24 bits to
    /// right-aligned values accepted by the observed Samsung encoder.
    /// Exact amplitude scaling still requires reference-vector verification.
    pub fn encode_msb_aligned_i32(
        &mut self,
        pcm: &[i32],
        output: &mut [u8],
    ) -> Result<usize, SscError> {
        self.encode_impl(pcm, output, true)
    }

    fn encode_impl(
        &mut self,
        pcm: &[i32],
        output: &mut [u8],
        shift_from_msb: bool,
    ) -> Result<usize, SscError> {
        let expected = self.config.pcm_values();
        if pcm.len() != expected {
            return Err(SscError::InputLength {
                expected,
                actual: pcm.len(),
            });
        }
        for (index, &sample) in pcm.iter().enumerate() {
            let shifted = if shift_from_msb { sample >> 8 } else { sample };
            let at = index * 4;
            self.pcm_scratch[at..at + 4].copy_from_slice(&shifted.to_le_bytes());
        }
        self.stream
            .write_all(&(self.pcm_scratch.len() as u32).to_le_bytes())?;
        self.stream.write_all(&self.pcm_scratch)?;
        let mut len_buf = [0u8; 4];
        self.stream.read_exact(&mut len_buf)?;
        let len = i32::from_le_bytes(len_buf);
        if len < 0 {
            return Err(SscError::Backend(len));
        }
        if !(4..=MAX_ENCODED_BYTES as i32).contains(&len) {
            return Err(SscError::Protocol(
                "encoded length outside negotiated limits",
            ));
        }
        let len = len as usize;
        self.stream.read_exact(&mut self.encoded_scratch[..len])?;
        if output.len() < len {
            return Err(SscError::OutputTooSmall {
                provided: output.len(),
                needed: len,
            });
        }
        output[..len].copy_from_slice(&self.encoded_scratch[..len]);
        Ok(len)
    }
}

impl Drop for EncoderClient {
    fn drop(&mut self) {
        let _ = self.stream.write_all(&0u32.to_le_bytes());
        let _ = self.stream.shutdown(Shutdown::Both);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn backend_mock_roundtrip() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        let thread = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut hello = [0u8; 28];
            stream.read_exact(&mut hello).unwrap();
            assert_eq!(&hello[..4], b"SSC1");
            assert_eq!(u32::from_le_bytes(hello[4..8].try_into().unwrap()), 48000);
            stream.write_all(b"SSCR").unwrap();
            stream.write_all(&0i32.to_le_bytes()).unwrap();
            stream.write_all(&9540i32.to_le_bytes()).unwrap();
            let mut count = [0u8; 4];
            stream.read_exact(&mut count).unwrap();
            assert_eq!(u32::from_le_bytes(count), 864 * 2 * 4);
            let mut pcm = vec![0u8; 864 * 2 * 4];
            stream.read_exact(&mut pcm).unwrap();
            assert_eq!(i32::from_le_bytes(pcm[0..4].try_into().unwrap()), -8388608);
            stream.write_all(&6i32.to_le_bytes()).unwrap();
            stream.write_all(b"\xff\xee\x10\x20\x30\x40").unwrap();
            stream.read_exact(&mut count).unwrap();
            assert_eq!(u32::from_le_bytes(count), 0);
        });
        let cfg = Config {
            sample_rate: 48000,
            channels: 2,
            depth: 24,
            bitrate: 328000,
            samples_per_channel: 864,
        };
        let mut encoder = EncoderClient::connect(addr, cfg).unwrap();
        assert_eq!(encoder.context_bytes, 9540);
        let mut pcm = vec![0i32; 864 * 2];
        pcm[0] = i32::MIN;
        let mut out = [0u8; 1024];
        let len = encoder.encode_msb_aligned_i32(&pcm, &mut out).unwrap();
        assert_eq!(len, 6);
        assert_eq!(&out[..6], b"\xff\xee\x10\x20\x30\x40");
        drop(encoder);
        thread.join().unwrap();
    }

    #[test]
    fn invalid_config_rejected() {
        let cfg = Config {
            sample_rate: 32000,
            channels: 2,
            depth: 24,
            bitrate: 328000,
            samples_per_channel: 864,
        };
        assert!(matches!(cfg.validate(), Err(SscError::InvalidConfig)));
    }
}

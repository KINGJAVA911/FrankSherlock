use std::path::Path;
use std::sync::OnceLock;

use reverse_geocoder::ReverseGeocoder;

static GEOCODER: OnceLock<ReverseGeocoder> = OnceLock::new();

fn geocoder() -> &'static ReverseGeocoder {
    GEOCODER.get_or_init(ReverseGeocoder::new)
}

/// Result of EXIF GPS extraction + reverse geocoding.
#[derive(Debug, Clone, Default)]
pub struct ExifLocation {
    #[allow(dead_code)] // Reserved for future map view
    pub latitude: Option<f64>,
    #[allow(dead_code)] // Reserved for future map view
    pub longitude: Option<f64>,
    pub location_text: String,
}

/// Main entry point: extract GPS coordinates from EXIF and reverse geocode.
pub fn extract_location(path: &Path) -> ExifLocation {
    let Some((lat, lon)) = extract_gps_coords(path) else {
        return ExifLocation::default();
    };
    let location_text = reverse_geocode(lat, lon);
    ExifLocation {
        latitude: Some(lat),
        longitude: Some(lon),
        location_text,
    }
}

/// Read EXIF GPS tags and convert DMS rational values to decimal degrees.
fn extract_gps_coords(path: &Path) -> Option<(f64, f64)> {
    let file = std::fs::File::open(path).ok()?;
    let mut buf_reader = std::io::BufReader::new(file);
    let exif = exif::Reader::new()
        .read_from_container(&mut buf_reader)
        .ok()?;

    let lat_field = exif.get_field(exif::Tag::GPSLatitude, exif::In::PRIMARY)?;
    let lat_ref_field = exif.get_field(exif::Tag::GPSLatitudeRef, exif::In::PRIMARY)?;
    let lon_field = exif.get_field(exif::Tag::GPSLongitude, exif::In::PRIMARY)?;
    let lon_ref_field = exif.get_field(exif::Tag::GPSLongitudeRef, exif::In::PRIMARY)?;

    let lat = parse_dms_to_decimal(&lat_field.value)?;
    let lon = parse_dms_to_decimal(&lon_field.value)?;

    let lat_ref = lat_ref_field.display_value().to_string();
    let lon_ref = lon_ref_field.display_value().to_string();

    let lat = if lat_ref.contains('S') { -lat } else { lat };
    let lon = if lon_ref.contains('W') { -lon } else { lon };

    Some((lat, lon))
}

/// Convert EXIF DMS (degrees/minutes/seconds) rational values to decimal degrees.
fn parse_dms_to_decimal(value: &exif::Value) -> Option<f64> {
    match value {
        exif::Value::Rational(v) if v.len() >= 3 => {
            let degrees = v[0].to_f64();
            let minutes = v[1].to_f64();
            let seconds = v[2].to_f64();
            Some(degrees + minutes / 60.0 + seconds / 3600.0)
        }
        _ => None,
    }
}

/// Reverse geocode coordinates to a human-readable location string.
fn reverse_geocode(lat: f64, lon: f64) -> String {
    let result = geocoder().search((lat, lon));
    let record = result.record;
    let mut parts = Vec::new();
    if !record.name.is_empty() {
        parts.push(record.name.as_str());
    }
    if !record.admin1.is_empty() {
        parts.push(record.admin1.as_str());
    }
    if !record.cc.is_empty() {
        parts.push(record.cc.as_str());
    }
    parts.join(", ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_dms_rational_values() {
        // 40 degrees, 44 minutes, 54.36 seconds = ~40.748433
        let value = exif::Value::Rational(vec![
            exif::Rational { num: 40, denom: 1 },
            exif::Rational { num: 44, denom: 1 },
            exif::Rational {
                num: 5436,
                denom: 100,
            },
        ]);
        let result = parse_dms_to_decimal(&value).expect("should parse");
        assert!((result - 40.7484333).abs() < 0.001);
    }

    #[test]
    fn parse_dms_empty_value() {
        let value = exif::Value::Rational(vec![]);
        assert!(parse_dms_to_decimal(&value).is_none());
    }

    #[test]
    fn parse_dms_wrong_type() {
        let value = exif::Value::Ascii(vec![b"hello".to_vec()]);
        assert!(parse_dms_to_decimal(&value).is_none());
    }

    #[test]
    fn reverse_geocode_known_coords() {
        // NYC area (Times Square approx)
        let result = reverse_geocode(40.758, -73.9855);
        assert!(!result.is_empty());
        // Should contain US country code
        assert!(result.contains("US"));
    }

    #[test]
    fn extract_location_non_image() {
        let tmp = tempfile::NamedTempFile::new().expect("tempfile");
        std::fs::write(tmp.path(), b"not an image").expect("write");
        let loc = extract_location(tmp.path());
        assert!(loc.latitude.is_none());
        assert!(loc.longitude.is_none());
        assert!(loc.location_text.is_empty());
    }

    #[test]
    fn extract_location_nonexistent_file() {
        let loc = extract_location(Path::new("/nonexistent/file.jpg"));
        assert!(loc.latitude.is_none());
        assert!(loc.location_text.is_empty());
    }
}

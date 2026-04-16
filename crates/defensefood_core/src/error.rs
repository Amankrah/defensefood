use pyo3::exceptions::PyValueError;
use pyo3::PyErr;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum DefenseFoodError {
    #[error("Data quality issue: {0}")]
    DataQuality(String),

    #[error("Division by zero: {0}")]
    DivisionByZero(String),

    #[error("Invalid input: {0}")]
    InvalidInput(String),

    #[error("Insufficient data: {0}")]
    InsufficientData(String),
}

impl From<DefenseFoodError> for PyErr {
    fn from(err: DefenseFoodError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

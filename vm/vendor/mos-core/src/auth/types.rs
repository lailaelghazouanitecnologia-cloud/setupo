//! Authentication types

use crate::core::SecurityType;

/// Authentication credentials
#[derive(Debug, Clone)]
pub enum Credentials {
    /// No credentials needed
    None,
    /// Password for VNC authentication
    Password(String),
    /// Username and password
    UsernamePassword { username: String, password: String },
}

impl Credentials {
    /// Create password credentials
    pub fn password(pwd: impl Into<String>) -> Self {
        Self::Password(pwd.into())
    }

    /// Create username/password credentials
    pub fn username_password(user: impl Into<String>, pwd: impl Into<String>) -> Self {
        Self::UsernamePassword {
            username: user.into(),
            password: pwd.into(),
        }
    }

    /// Get password if available
    pub fn get_password(&self) -> Option<&str> {
        match self {
            Self::Password(pwd) => Some(pwd),
            Self::UsernamePassword { password, .. } => Some(password),
            Self::None => None,
        }
    }
}

/// Maps SecurityType to required credentials
pub fn required_credentials(security_type: SecurityType) -> Option<Credentials> {
    match security_type {
        SecurityType::None => None,
        SecurityType::VncAuth => Some(Credentials::None), // Will be filled later
        _ => Some(Credentials::None),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_credentials() {
        let creds = Credentials::password("secret");
        assert_eq!(creds.get_password(), Some("secret"));

        let creds = Credentials::username_password("user", "pass");
        assert_eq!(creds.get_password(), Some("pass"));

        let creds = Credentials::None;
        assert_eq!(creds.get_password(), None);
    }
}

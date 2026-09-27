package com.revayato.app.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(
    /** Email or username — the backend accepts either as the identifier. */
    val login: String,
    val password: String,
)

@Serializable
data class RegisterRequest(
    val email: String,
    val username: String,
    val password: String,
)

@Serializable
data class RefreshRequest(
    val refresh: String,
)

@Serializable
data class RefreshResponse(
    val access: String,
    val refresh: String? = null,
)

@Serializable
data class TokenResponse(
    val access: String,
    val refresh: String,
    val user: UserDto? = null,
)

@Serializable
data class UserDto(
    val id: Int = 0,
    val email: String = "",
    val username: String = "",
    @SerialName("is_verified") val isVerified: Boolean = false,
    @SerialName("is_staff") val isStaff: Boolean = false,
    @SerialName("is_superuser") val isSuperuser: Boolean = false,
    val profile: ProfileDto? = null,
)

@Serializable
data class ProfileDto(
    val avatar: String? = null,
    val bio: String? = null,
    @SerialName("preferred_language") val preferredLanguage: String? = null,
    @SerialName("is_email_verified") val isEmailVerified: Boolean = false,
)

@Serializable
data class PasswordResetRequest(val email: String)

@Serializable
data class MessageResponse(val detail: String? = null, val message: String? = null)

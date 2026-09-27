package com.revayato.app.core.network

import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import retrofit2.HttpException
import java.io.IOException

sealed interface ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>
    data class Error(val message: String, val code: Int? = null) : ApiResult<Nothing>
}

inline fun <T> ApiResult<T>.onSuccess(block: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Success) block(data)
    return this
}

inline fun <T> ApiResult<T>.onError(block: (String, Int?) -> Unit): ApiResult<T> {
    if (this is ApiResult.Error) block(message, code)
    return this
}

/** Returns the payload on success, or null on error. */
fun <T> ApiResult<T>.orNull(): T? = (this as? ApiResult.Success)?.data

private val errorJson = Json { ignoreUnknownKeys = true; isLenient = true }

/**
 * Wraps a suspending network call, converting transport and HTTP failures into a
 * localized [ApiResult.Error]. Cancellation is rethrown so structured concurrency
 * still works.
 */
suspend fun <T> safeApiCall(block: suspend () -> T): ApiResult<T> = try {
    ApiResult.Success(block())
} catch (e: CancellationException) {
    throw e
} catch (e: HttpException) {
    ApiResult.Error(parseHttpError(e), e.code())
} catch (e: IOException) {
    ApiResult.Error("اتصال به اینترنت برقرار نشد. دوباره تلاش کن.")
} catch (e: Exception) {
    ApiResult.Error(e.message ?: "خطای ناشناخته رخ داد.")
}

fun parseHttpError(e: HttpException): String {
    val raw = try {
        e.response()?.errorBody()?.string()
    } catch (_: Exception) {
        null
    }
    if (!raw.isNullOrBlank()) {
        try {
            val obj = errorJson.parseToJsonElement(raw).jsonObject
            // Primary human message + an actionable hint when the backend supplies
            // one (e.g. "رمز عبور درست نیست." + "از بازیابی رمز عبور استفاده کن.").
            val primary = firstText(obj["detail"] ?: obj["message"] ?: obj["error"])
            val hint = firstText(obj["hint"])
            if (primary != null) {
                return if (hint != null && hint != primary) "$primary\n$hint" else primary
            }
            // DRF validation errors: {"field": ["msg", …]} / {"non_field_errors": […]}.
            // Prefer non_field_errors, then the first field's first message.
            firstText(obj["non_field_errors"])?.let { return it }
            for (element in obj.values) {
                firstText(element)?.let { return it }
            }
        } catch (_: Exception) {
            // fall through to status mapping
        }
    }
    return when (e.code()) {
        400 -> "اطلاعات واردشده معتبر نیست. ورودی‌ها را بررسی کن."
        401 -> "ایمیل/نام کاربری یا رمز عبور نادرست است."
        403 -> "به این بخش دسترسی نداری."
        404 -> "حسابی با این مشخصات پیدا نشد. می‌توانی ثبت‌نام کنی."
        423 -> "حساب موقتاً قفل شده است. کمی بعد دوباره تلاش کن یا رمز را بازیابی کن."
        429 -> "تعداد تلاش‌ها زیاد شد. کمی صبر کن و دوباره امتحان کن."
        in 500..599 -> "خطای سرور. کمی بعد دوباره امتحان کن."
        else -> "خطایی رخ داد (${e.code()})."
    }
}

/** Pull a readable message from a JSON value that may be a string, or a DRF
 *  error array like ["message", …], recursing into nested arrays/objects. */
private fun firstText(element: JsonElement?): String? = when (element) {
    null -> null
    is JsonPrimitive -> element.content.takeIf { it.isNotBlank() && element.isString }
    is JsonArray -> element.firstNotNullOfOrNull { firstText(it) }
    is JsonObject -> element.values.firstNotNullOfOrNull { firstText(it) }
    else -> null
}

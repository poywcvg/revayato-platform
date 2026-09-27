package com.revayato.app.core.update

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton
import kotlin.coroutines.coroutineContext

/** Where a downloaded installer waits between the download and the tap on «نصب». */
private const val UPDATE_DIR = "updates"

/** MIME type the system package installer answers to. */
private const val APK_MIME = "application/vnd.android.package-archive"

/**
 * Fetches the update APK and hands it to the system installer.
 *
 * Two things make this different from an ordinary file download. First, the
 * bytes are executable: a truncated or swapped file must never reach the
 * installer, so the server's SHA-256 is checked before the install intent is
 * built and a mismatch deletes the file. Second, installing an APK from inside
 * an app needs `REQUEST_INSTALL_PACKAGES` *and* the user's per-app permission on
 * Android 8+, which cannot be granted in-process — [canInstall] reports it and
 * [unknownSourcesSettings] takes the user to the one screen that grants it.
 */
@Singleton
class ApkInstaller @Inject constructor(
    @ApplicationContext private val context: Context,
    @Named("apk") private val client: OkHttpClient,
) {

    /** True when the system will let us start an install without a detour. */
    fun canInstall(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            context.packageManager.canRequestPackageInstalls()

    /** The per-app "install unknown apps" screen for Revayato. */
    fun unknownSourcesSettings(): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))

    /**
     * Downloads [url] into the cache and returns the finished file.
     *
     * [onProgress] receives 0..100, or -1 while the total length is unknown.
     * Throws [IOException] on a transport failure, a short read, or a checksum
     * that does not match [sha256] (empty [sha256] skips the check).
     */
    suspend fun download(
        url: String,
        versionCode: Int,
        expectedBytes: Long,
        sha256: String,
        onProgress: (Int) -> Unit,
    ): File = withContext(Dispatchers.IO) {
        val dir = File(context.cacheDir, UPDATE_DIR).apply { mkdirs() }
        // One file per build, so a re-check never installs yesterday's download.
        val target = File(dir, "revayato-$versionCode.apk")
        val partial = File(dir, "revayato-$versionCode.apk.part")
        purgeExcept(dir, target.name, partial.name)

        if (target.isFile && target.length() > 0 && matches(target, sha256)) {
            // Already fetched — a failed install attempt should not re-download.
            onProgress(100)
            return@withContext target
        }
        target.delete()
        partial.delete()

        val response = client.newCall(Request.Builder().url(url).build()).execute()
        response.use {
            if (!it.isSuccessful) throw IOException("HTTP ${it.code}")
            val body = it.body ?: throw IOException("empty body")
            val total = body.contentLength().takeIf { len -> len > 0 } ?: expectedBytes
            var written = 0L
            var lastReported = -1
            body.byteStream().use { input ->
                partial.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        coroutineContext.ensureActive()
                        val read = input.read(buffer)
                        if (read <= 0) break
                        output.write(buffer, 0, read)
                        written += read
                        val percent = if (total > 0) ((written * 100) / total).toInt().coerceIn(0, 100) else -1
                        if (percent != lastReported) {
                            lastReported = percent
                            onProgress(percent)
                        }
                    }
                }
            }
            if (expectedBytes > 0 && written != expectedBytes) {
                partial.delete()
                throw IOException("short read: $written of $expectedBytes")
            }
        }

        if (!matches(partial, sha256)) {
            partial.delete()
            throw IOException("checksum mismatch")
        }
        if (!partial.renameTo(target)) {
            partial.delete()
            throw IOException("could not finalize download")
        }
        onProgress(100)
        target
    }

    /**
     * The intent that opens the system installer for [file].
     *
     * A `file://` URI would trip `FileUriExposedException` from Android 7 on, so
     * the APK is handed over through the FileProvider declared in the manifest,
     * with a one-shot read grant attached to the intent.
     */
    fun installIntent(file: File): Intent {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.updates", file)
        return Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, APK_MIME)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
    }

    /**
     * Deletes installers for builds at or below [versionCode] — those are either
     * already running or superseded. A download waiting for a *newer* build is
     * left in place so backgrounding the app between the download and the tap on
     * «نصب» does not cost the bytes twice.
     */
    fun purgeUpTo(versionCode: Int) {
        val dir = File(context.cacheDir, UPDATE_DIR)
        dir.listFiles()?.forEach { file ->
            val code = file.name.removePrefix("revayato-").substringBefore('.').toIntOrNull()
            if (code == null || code <= versionCode) file.delete()
        }
    }

    /** Drops installers left behind by earlier versions or abandoned downloads. */
    private fun purgeExcept(dir: File, vararg keep: String) {
        dir.listFiles()?.forEach { file ->
            if (file.isFile && file.name !in keep) file.delete()
        }
    }

    private fun matches(file: File, sha256: String): Boolean {
        if (sha256.isBlank()) return true  // server could not hash it; size check stands alone
        if (!file.isFile) return false
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }.equals(sha256, ignoreCase = true)
    }
}

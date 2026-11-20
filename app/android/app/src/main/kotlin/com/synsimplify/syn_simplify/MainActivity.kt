package com.synsimplify.syn_simplify

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.Settings
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val channelName = "synsimplify/native"
    private var pendingFolder: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "paths" -> result.success(storagePaths())
                    "isAllFiles" -> result.success(hasAllFiles())
                    "requestAllFiles" -> {
                        requestAllFiles()
                        result.success(true)
                    }
                    "pickFolder" -> pickFolder(result)
                    "keepAwake" -> {
                        val on = call.argument<Boolean>("on") ?: false
                        keepAwake(on)
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    private fun storagePaths(): Map<String, String> {
        val root = Environment.getExternalStorageDirectory()?.absolutePath ?: "/storage/emulated/0"
        val app = getExternalFilesDir(null)?.absolutePath ?: filesDir.absolutePath
        return mapOf("root" to root, "app" to app)
    }

    private fun hasAllFiles(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Environment.isExternalStorageManager()
        } else {
            checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun requestAllFiles() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                val intent = Intent(
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:$packageName")
                )
                startActivity(intent)
            } catch (e: Exception) {
                try {
                    startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
                } catch (_: Exception) {
                }
            }
        } else {
            requestPermissions(
                arrayOf(
                    Manifest.permission.READ_EXTERNAL_STORAGE,
                    Manifest.permission.WRITE_EXTERNAL_STORAGE
                ),
                4002
            )
        }
    }

    private fun pickFolder(result: MethodChannel.Result) {
        pendingFolder = result
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
            addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
            )
        }
        try {
            startActivityForResult(intent, REQ_PICK_FOLDER)
        } catch (e: Exception) {
            pendingFolder = null
            result.success(null)
        }
    }

    private fun keepAwake(on: Boolean) {
        runOnUiThread {
            if (on) {
                window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            } else {
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_PICK_FOLDER) return
        val uri: Uri? = data?.data
        var path: String? = null
        if (uri != null) {
            path = treeToPath(uri)
            try {
                contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                )
            } catch (_: Exception) {
            }
        }
        pendingFolder?.success(path)
        pendingFolder = null
    }

    /**
     * content://com.android.externalstorage.documents/tree/primary%3ADownload
     * → /storage/emulated/0/Download
     *
     * App 已经拿了「所有文件访问」，所以拿到真实路径后可以直接用 java.io.File 读写。
     */
    private fun treeToPath(uri: Uri): String? {
        return try {
            if (uri.authority != "com.android.externalstorage.documents") return null
            val docId = DocumentsContract.getTreeDocumentId(uri)
            val split = docId.split(":", limit = 2)
            val type = split[0]
            val rel = if (split.size > 1) split[1] else ""
            val base = if (type.equals("primary", true)) {
                Environment.getExternalStorageDirectory().absolutePath
            } else {
                "/storage/$type"
            }
            if (rel.isEmpty()) base else "$base/$rel"
        } catch (e: Exception) {
            null
        }
    }

    companion object {
        private const val REQ_PICK_FOLDER = 4001
    }
}

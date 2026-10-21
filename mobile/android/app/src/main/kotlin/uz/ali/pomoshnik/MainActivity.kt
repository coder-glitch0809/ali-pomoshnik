package uz.ali.pomoshnik

import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/** Boshqa ilovalarni boshqarish (faqat "full" versiyada AliAccessibilityService o'zini shu yerga ulaydi). */
interface DeviceController {
    fun global(target: String): String
    fun clickText(text: String): String
    fun typeText(text: String): String
}

object DeviceControl {
    @Volatile
    var controller: DeviceController? = null
}

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "uz.ali/device").setMethodCallHandler { call, result ->
            val target = call.argument<String>("target") ?: ""
            when (call.method) {
                "openApp" -> result.success(openApp(call.argument<String>("name") ?: ""))
                "openSettings" -> result.success(openSettings(target))
                "accessibilityEnabled" -> result.success(DeviceControl.controller != null && accessibilityOn())
                "openAccessibilitySettings" -> {
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    result.success(null)
                }
                "global", "click_text", "type_text" -> {
                    val c = DeviceControl.controller
                    if (c == null) {
                        result.success("Boshqaruv xizmati yoqilmagan")
                    } else {
                        result.success(
                            when (call.method) {
                                "global" -> c.global(target)
                                "click_text" -> c.clickText(target)
                                else -> c.typeText(target)
                            }
                        )
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun accessibilityOn(): Boolean {
        val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        return enabled.contains(packageName)
    }

    /** Ilovani nomi (yoki paket nomi) bo'yicha topib ochadi. AndroidManifest'dagi <queries> launcher ilovalarni ko'rsatadi. */
    private fun openApp(name: String): String {
        val query = name.trim().lowercase()
        if (query.isEmpty()) return "Ilova nomi berilmadi"
        val pm = packageManager
        pm.getLaunchIntentForPackage(name.trim())?.let {
            startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return "Ochildi"
        }
        val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val apps = pm.queryIntentActivities(launcher, PackageManager.MATCH_ALL)
        val match = apps.firstOrNull { it.loadLabel(pm).toString().lowercase() == query }
            ?: apps.firstOrNull { it.loadLabel(pm).toString().lowercase().contains(query) }
            ?: apps.firstOrNull { it.activityInfo.packageName.lowercase().contains(query) }
            ?: return "“$name” ilovasi topilmadi"
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            .setComponent(ComponentName(match.activityInfo.packageName, match.activityInfo.name))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
        return "${match.loadLabel(pm)} ochildi"
    }

    private fun openSettings(target: String): String {
        val action = when (target) {
            "wifi" -> Settings.ACTION_WIFI_SETTINGS
            "bluetooth" -> Settings.ACTION_BLUETOOTH_SETTINGS
            "location" -> Settings.ACTION_LOCATION_SOURCE_SETTINGS
            "display" -> Settings.ACTION_DISPLAY_SETTINGS
            "sound" -> Settings.ACTION_SOUND_SETTINGS
            "apps" -> Settings.ACTION_APPLICATION_SETTINGS
            "battery" -> Intent.ACTION_POWER_USAGE_SUMMARY
            else -> Settings.ACTION_SETTINGS
        }
        return try {
            startActivity(Intent(action).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            "Sozlamalar ochildi"
        } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            "Asosiy sozlamalar ochildi"
        }
    }
}

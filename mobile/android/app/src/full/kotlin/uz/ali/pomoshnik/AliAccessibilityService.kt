package uz.ali.pomoshnik

import android.accessibilityservice.AccessibilityService
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Faqat "full" (saytdan yuklanadigan APK) versiyada: foydalanuvchi buyurganda boshqa ilovalarda tugma bosadi,
 * matn yozadi va tizim amallarini bajaradi. Ekrandagi matn faqat telefonda o'qiladi, hech qayerga yuborilmaydi.
 * Foydalanuvchi uni Sozlamalar -> Maxsus imkoniyatlar -> Ali da o'zi yoqadi.
 */
class AliAccessibilityService : AccessibilityService(), DeviceController {
    override fun onServiceConnected() {
        DeviceControl.controller = this
    }

    override fun onUnbind(intent: android.content.Intent?): Boolean {
        if (DeviceControl.controller === this) DeviceControl.controller = null
        return super.onUnbind(intent)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() {}

    override fun global(target: String): String {
        val action = when (target) {
            "back" -> GLOBAL_ACTION_BACK
            "home" -> GLOBAL_ACTION_HOME
            "recents" -> GLOBAL_ACTION_RECENTS
            "notifications" -> GLOBAL_ACTION_NOTIFICATIONS
            "quick_settings" -> GLOBAL_ACTION_QUICK_SETTINGS
            else -> return "Noma’lum amal: $target"
        }
        return if (performGlobalAction(action)) "Bajarildi" else "Bajarib bo‘lmadi"
    }

    override fun clickText(text: String): String {
        val root = rootInActiveWindow ?: return "Ekran o‘qilmadi"
        val nodes = root.findAccessibilityNodeInfosByText(text)
        for (node in nodes) {
            var n: AccessibilityNodeInfo? = node
            while (n != null && !n.isClickable) n = n.parent
            if (n != null && n.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return "“$text” bosildi"
        }
        return "Ekranda “$text” topilmadi"
    }

    override fun typeText(text: String): String {
        val root = rootInActiveWindow ?: return "Ekran o‘qilmadi"
        val field = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: findEditable(root)
            ?: return "Yozish maydoni topilmadi"
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return if (field.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) "Yozildi" else "Yozib bo‘lmadi"
    }

    private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            findEditable(child)?.let { return it }
        }
        return null
    }
}

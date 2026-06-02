/*示範程式碼*/
fun nodeToMap(node: AccessibilityNodeInfo?): Map<String, Any>? {
    if (node == null) return null

    val bounds = Rect()
    node.getBoundsInScreen(bounds)

    val map = mutableMapOf<String, Any>(
        "class_name"    to (node.className?.toString() ?: ""),
        "text"          to (node.text?.toString() ?: ""),
        "content_desc"  to (node.contentDescription?.toString() ?: ""),
        "resource_id"   to (node.viewIdResourceName ?: ""),
        "is_clickable"  to node.isClickable,
        "is_editable"   to node.isEditable,
        "is_enabled"    to node.isEnabled,
        "bounds"        to mapOf(
            "left" to bounds.left, "top" to bounds.top,
            "right" to bounds.right, "bottom" to bounds.bottom
        )
    )

    val children = (0 until node.childCount)
        .mapNotNull { nodeToMap(node.getChild(it)) }
    if (children.isNotEmpty()) map["children"] = children

    return map
}
/*----------------------------------------------------------------------- */
/*輸出結果應為巢狀的dict */
/*底下為輸出範例 */
{
  "class_name": "android.widget.FrameLayout",
  "text": "",
  "resource_id": "com.example:id/root",
  "is_clickable": false,
  "bounds": {"left": 0, "top": 0, "right": 1080, "bottom": 2400},
  "children": [
    {
      "class_name": "android.widget.EditText",
      "text": "",
      "resource_id": "com.example:id/search_bar",
      "is_clickable": true,
      "is_editable": true,
      "bounds": {"left": 32, "top": 120, "right": 1048, "bottom": 200},
      "children": []
    }
  ]
}
/*只保留有意義的節點 */
val isUseful = node.isClickable 
    || node.isEditable    /*節點的可編輯性，例如輸入框 */
    || !node.text.isNullOrBlank()     /*有文字的節點，表示一些資訊 */
    || !node.contentDescription.isNullOrBlank()   /*沒有文字但有描述的節點，例如購物車圖示 */
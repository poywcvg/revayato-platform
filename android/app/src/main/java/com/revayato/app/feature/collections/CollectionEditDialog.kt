package com.revayato.app.feature.collections

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Link
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Public
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.data.model.CollectionVisibility
import com.revayato.app.ui.components.RevayatoSpinner

/**
 * Create/edit form for a collection: name, optional description and a
 * three-way visibility picker (public / by-link / private). Reused by the
 * my-collections list (create) and the collection detail (edit).
 */
@Composable
fun CollectionEditDialog(
    title: String,
    confirmLabel: String,
    initialName: String,
    initialDescription: String,
    initialVisibility: String,
    busy: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onConfirm: (name: String, description: String, visibility: String) -> Unit,
) {
    var name by remember { mutableStateOf(initialName) }
    var description by remember { mutableStateOf(initialDescription) }
    var visibility by remember { mutableStateOf(initialVisibility) }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(name.trim(), description.trim(), visibility) },
                enabled = !busy && name.isNotBlank(),
            ) {
                if (busy) {
                    RevayatoSpinner(size = 18.dp, color = BrandMint)
                } else {
                    Text(confirmLabel, color = BrandMint, fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !busy) {
                Text("انصراف", color = TextMuted)
            }
        },
        title = { Text(title, fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.take(120) },
                    label = { Text("نام کالکشن") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it.take(2000) },
                    label = { Text("توضیح (اختیاری)") },
                    minLines = 2,
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("چه کسانی ببینند؟", style = MaterialTheme.typography.labelLarge, color = TextMuted)
                VisibilityOption(
                    icon = Icons.Rounded.Public,
                    label = "عمومی",
                    hint = "روی پروفایلت دیده می‌شود",
                    selected = visibility == CollectionVisibility.PUBLIC,
                    onClick = { visibility = CollectionVisibility.PUBLIC },
                )
                VisibilityOption(
                    icon = Icons.Rounded.Link,
                    label = "فقط با لینک",
                    hint = "هرکس لینک را دارد می‌بیند",
                    selected = visibility == CollectionVisibility.UNLISTED,
                    onClick = { visibility = CollectionVisibility.UNLISTED },
                )
                VisibilityOption(
                    icon = Icons.Rounded.Lock,
                    label = "خصوصی",
                    hint = "فقط خودت",
                    selected = visibility == CollectionVisibility.PRIVATE,
                    onClick = { visibility = CollectionVisibility.PRIVATE },
                )
                if (error != null) {
                    Text(error, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
    )
}

@Composable
private fun VisibilityOption(
    icon: ImageVector,
    label: String,
    hint: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val border = if (selected) BrandMint else MaterialTheme.colorScheme.outline.copy(alpha = 0.4f)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(if (selected) 1.5.dp else 1.dp, border, RoundedCornerShape(12.dp))
            .background(if (selected) BrandMint.copy(alpha = 0.08f) else MaterialTheme.colorScheme.surface)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = if (selected) BrandMint else TextMuted,
            modifier = Modifier.size(20.dp),
        )
        Column(Modifier.weight(1f)) {
            Text(label, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
            Text(hint, style = MaterialTheme.typography.labelSmall, color = TextMuted)
        }
        if (selected) {
            Spacer(Modifier.size(6.dp))
            Text("✓", color = BrandMint, fontWeight = FontWeight.Black)
        }
    }
}

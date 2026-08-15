<script setup lang="ts">
import Loader from '~icons/lucide/loader-circle'

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit'
  to?: string
}>(), { variant: 'primary', size: 'md', loading: false, disabled: false, type: 'button', to: '' })

const component = computed(() => props.to ? resolveComponent('NuxtLink') : 'button')

function guardDisabledLink(event: MouseEvent) {
  if (props.to && (props.disabled || props.loading)) event.preventDefault()
}
</script>

<template>
  <component
    :is="component"
    :type="to ? undefined : type"
    :to="to || undefined"
    :disabled="to ? undefined : disabled || loading"
    :aria-disabled="to && (disabled || loading) ? 'true' : undefined"
    :tabindex="to && (disabled || loading) ? -1 : undefined"
    class="admin-focus inline-flex items-center justify-center gap-2 rounded-xl font-extrabold disabled:cursor-not-allowed disabled:opacity-55"
    :class="[
      size === 'sm' ? 'min-h-11 px-3 text-xs' : 'min-h-11 px-4 text-sm',
      (disabled || loading) && 'cursor-not-allowed opacity-55',
      variant === 'primary' && 'bg-[var(--admin-primary)] text-white shadow-[0_8px_24px_rgb(var(--admin-primary-rgb)/16%)] hover:bg-[var(--admin-primary-hover)]',
      variant === 'secondary' && 'border border-[var(--admin-border)] bg-[var(--admin-surface)] text-[var(--admin-primary)] hover:border-[var(--admin-accent)]/45 hover:bg-[var(--admin-surface-muted)]',
      variant === 'ghost' && 'text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)] hover:text-[var(--admin-primary)]',
      variant === 'danger' && 'border border-red-200 bg-red-50 text-[var(--admin-danger)] hover:bg-red-100',
    ]"
    @click="guardDisabledLink"
  >
    <Loader v-if="loading" class="size-4 animate-spin" aria-hidden="true" />
    <slot name="icon" />
    <slot />
  </component>
</template>

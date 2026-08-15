<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'draft' | 'published' | 'archived' | 'tmdb' | 'warning' | 'neutral' | 'queued' | 'running' | 'cancelling' | 'cancelled' | 'succeeded' | 'failed' }>(), { tone: 'neutral' })
</script>

<template>
  <span
    class="inline-flex min-h-6 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-extrabold leading-5"
    :class="[
      'admin-badge',
      `admin-badge--${tone}`,
    ]"
  ><span class="size-1.5 rounded-full bg-current opacity-75" aria-hidden="true" /><slot /></span>
</template>

<style scoped>
/* Tone colours are derived from the admin design tokens so badges stay consistent
   with the rest of the panel (was a hard-coded Tailwind palette). */
.admin-badge {
  color: var(--admin-muted);
  background: var(--admin-surface-muted);
  border-color: color-mix(in srgb, var(--admin-muted) 30%, transparent);
}

.admin-badge--draft,
.admin-badge--queued {
  color: #92400e;
  background: #fffbeb;
  border-color: #fde68a;
}

.admin-badge--published,
.admin-badge--succeeded {
  color: #065f46;
  background: #ecfdf5;
  border-color: #a7f3d0;
}

.admin-badge--archived,
.admin-badge--neutral,
.admin-badge--cancelled {
  color: var(--admin-muted);
  background: var(--admin-surface-muted);
  border-color: var(--admin-border);
}

.admin-badge--tmdb,
.admin-badge--running {
  color: #115e59;
  background: #f0fdfa;
  border-color: #99f6e4;
}

.admin-badge--warning,
.admin-badge--cancelling {
  color: #9a3412;
  background: #fff7ed;
  border-color: #fed7aa;
}

.admin-badge--failed {
  color: var(--admin-danger);
  background: #fef2f2;
  border-color: #fecaca;
}
</style>

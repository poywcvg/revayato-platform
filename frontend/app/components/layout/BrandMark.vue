<script setup lang="ts">
// Inline so the arch can follow the theme (cream on dark, burnt brown on light).
// Geometry mirrors /assets/brand/logo.svg; keep both in sync.
const id = useId()
</script>

<template>
  <svg viewBox="112 70 288 374" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <defs>
      <linearGradient :id="`${id}-f`" x1="0" y1="150" x2="0" y2="394" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="#e4572e" />
        <stop offset=".55" stop-color="#f29f3d" />
        <stop offset="1" stop-color="#ffc76b" />
      </linearGradient>
      <linearGradient :id="`${id}-a`" x1="0" y1="90" x2="0" y2="424" gradientUnits="userSpaceOnUse">
        <stop offset="0" style="stop-color: var(--brand-arch-top, #fff1dc)" />
        <stop offset="1" style="stop-color: var(--brand-arch-bottom, #ffc76b)" />
      </linearGradient>
    </defs>
    <path d="M132 424 V252 C132 184 194 134 256 90 C318 134 380 184 380 252 V424" fill="none" :stroke="`url(#${id}-a)`" stroke-width="30" stroke-linecap="round" stroke-miterlimit="12" />
    <path d="M256 150 C262 198 336 236 336 312 C336 358 300 394 256 394 C212 394 176 358 176 312 C176 270 200 244 218 222 C220 244 230 258 244 264 C236 226 240 184 256 150 Z M236 298 L236 346 Q236 356 244.6 350.9 L285.4 327.1 Q294 322 285.4 316.9 L244.6 293.1 Q236 288 236 298 Z" :fill="`url(#${id}-f)`" fill-rule="evenodd" />
  </svg>
</template>

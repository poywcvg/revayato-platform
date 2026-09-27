<template>
  <div class="route-motion" aria-hidden="true">
    <span class="route-motion__veil" />
    <span class="route-motion__beam" />
    <span class="route-motion__beam route-motion__beam--echo" />
    <span class="route-motion__glow" />
  </div>
</template>

<style scoped>
.route-motion {
  position: fixed;
  inset: 0;
  z-index: 9998;
  overflow: hidden;
  pointer-events: none;
  visibility: hidden;
  opacity: 0;
  contain: strict;
  transition: visibility 0s linear 160ms, opacity 55ms ease 70ms;
}

.route-motion__veil {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(100deg, transparent 10%, rgb(228 173 73 / 4%) 48%, transparent 82%),
    linear-gradient(180deg, rgb(13 13 13 / 10%), transparent 24%);
  opacity: 0;
}

.route-motion__beam {
  position: absolute;
  top: 0;
  right: -28%;
  width: 28%;
  height: 2px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, #f6d58b 45%, #e4ad49 75%, transparent);
  box-shadow: 0 0 12px rgb(228 173 73 / 48%);
  transform: translate3d(0, 0, 0);
}

.route-motion__beam--echo {
  top: 3px;
  height: 1px;
  opacity: .45;
  filter: none;
}

.route-motion__glow {
  position: absolute;
  top: -6rem;
  right: -7rem;
  width: min(26rem, 72vw);
  aspect-ratio: 2 / 1;
  border-radius: 50%;
  background: radial-gradient(circle, rgb(228 173 73 / 11%), transparent 68%);
  opacity: 0;
  transform: scale(.75);
}

:global(html[data-page-navigating]) .route-motion {
  visibility: visible;
  opacity: 1;
  transition: opacity 30ms linear;
}

:global(html[data-page-navigating]) .route-motion__beam {
  animation: route-beam 260ms cubic-bezier(.2, .75, .25, 1) both;
}

:global(html[data-page-navigating]) .route-motion__beam--echo {
  animation-delay: 24ms;
}

:global(html[data-page-navigating]) .route-motion__veil {
  animation: route-veil 210ms ease-out both;
}

:global(html[data-page-navigating]) .route-motion__glow {
  animation: route-glow 230ms cubic-bezier(.22, 1, .36, 1) both;
}

@keyframes route-beam {
  0% { transform: translate3d(0, 0, 0); opacity: 0; }
  12% { opacity: 1; }
  100% { transform: translate3d(-470%, 0, 0); opacity: 0; }
}

@keyframes route-veil {
  0% { opacity: 0; transform: translate3d(5%, 0, 0); }
  38% { opacity: 1; }
  100% { opacity: 0; transform: translate3d(-5%, 0, 0); }
}

@keyframes route-glow {
  0% { opacity: 0; transform: scale(.75); }
  45% { opacity: 1; }
  100% { opacity: 0; transform: scale(1.15); }
}

@media (prefers-reduced-motion: reduce) {
  .route-motion { display: none; }
}
</style>

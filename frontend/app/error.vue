<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()
const status = computed(() => Number(props.error.statusCode) || 500)
const isNotFound = computed(() => status.value === 404)
const content = computed(() => {
  if (isNotFound.value) return { eyebrow: 'پایان غیرمنتظره', title: 'این سکانس توی فیلم نبود!', message: 'هرچی آرشیو را گشتیم، این صفحه پیدا نشد. شاید آدرس جابه‌جا شده یا قصه از مسیر دیگری ادامه دارد.' }
  if (status.value === 401) return { eyebrow: 'ورود لازم است', title: 'بلیتت را جا گذاشتی', message: 'برای ورود به این سالن باید اول وارد حساب کاربری‌ات شوی.' }
  if (status.value === 403) return { eyebrow: 'دسترسی محدود', title: 'این سالن خصوصی است', message: 'حساب تو اجازه دیدن این بخش را ندارد. اگر اشتباهی شده با پشتیبانی تماس بگیر.' }
  return { eyebrow: 'وقفه در پخش', title: 'آپارات فعلاً گیر کرده', message: 'یک مشکل موقت پیش آمده. چند لحظه بعد دوباره تلاش کن.' }
})

function goHome() { clearError({ redirect: '/' }) }
function retry() { if (import.meta.client) window.location.reload() }
useSeoMeta({ title: () => isNotFound.value ? 'صفحه پیدا نشد' : content.value.title })
</script>

<template>
  <div class="error-scene cinematic-app min-h-dvh overflow-hidden bg-canvas text-ink">
    <div class="error-scene__glow" aria-hidden="true" />
    <div class="error-scene__grain" aria-hidden="true" />
    <header class="error-scene__header">
      <AppLogo :compact-on-mobile="false" />
      <span class="error-scene__ticket"><i />سالن {{ isNotFound ? '۴۰۴' : status }}</span>
    </header>

    <main class="error-scene__stage">
      <section class="error-scene__copy">
        <p class="error-scene__eyebrow"><span />{{ content.eyebrow }}</p>
        <div v-if="isNotFound" class="error-scene__number" aria-label="خطای ۴۰۴">
          <span>۴</span><span class="error-scene__reel"><i /><i /><i /><i /></span><span>۴</span>
        </div>
        <p v-else class="error-scene__number error-scene__number--latin">{{ status }}</p>
        <h1>{{ content.title }}</h1>
        <p class="error-scene__message">{{ content.message }}</p>
        <div class="error-scene__actions">
          <button type="button" class="ui-primary-button" @click="goHome"><CinematicIcon name="home" class="size-4.5" /> برگشت به صفحه اصلی</button>
          <NuxtLink v-if="isNotFound" to="/search" class="ui-secondary-button"><CinematicIcon name="search" class="size-4.5" /> جستجو در آرشیو</NuxtLink>
          <button v-else type="button" class="ui-secondary-button" @click="retry"><CinematicIcon name="refresh" class="size-4.5" /> تلاش دوباره</button>
        </div>
      </section>

      <div class="error-scene__projector" aria-hidden="true">
        <div class="error-scene__beam" />
        <div class="error-scene__machine">
          <span class="error-scene__wheel error-scene__wheel--one"><i /><i /><i /><i /><i /></span>
          <span class="error-scene__wheel error-scene__wheel--two"><i /><i /><i /><i /><i /></span>
          <span class="error-scene__lens" /><span class="error-scene__body" /><span class="error-scene__leg" />
        </div>
      </div>
    </main>
    <p class="error-scene__footer">روایت هنوز ادامه دارد <span>•</span> فقط این فریم گم شده</p>
  </div>
</template>

<style scoped>
.error-scene{position:relative;isolation:isolate;background:radial-gradient(circle at 72% 38%,#332323 0,transparent 32%),linear-gradient(145deg,#17171b 0%,#0e0e11 72%)}
.error-scene__glow{position:absolute;inset:-20%;z-index:-2;background:radial-gradient(ellipse at 15% 15%,rgba(234,78,67,.1),transparent 28%),radial-gradient(ellipse at 85% 90%,rgba(226,172,91,.07),transparent 30%)}
.error-scene__grain{position:absolute;inset:0;z-index:5;pointer-events:none;opacity:.055;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.8'/%3E%3C/svg%3E")}
.error-scene__header{display:flex;align-items:center;justify-content:space-between;width:min(1180px,calc(100% - 40px));margin:auto;padding-top:28px}.error-scene__ticket{display:flex;align-items:center;gap:10px;border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:8px 14px;color:#aaa5a5;font-size:12px;background:rgba(255,255,255,.035);backdrop-filter:blur(8px)}.error-scene__ticket i{width:7px;height:7px;border-radius:50%;background:#df5149;box-shadow:0 0 16px #df5149}
.error-scene__stage{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(300px,.95fr);align-items:center;width:min(1180px,calc(100% - 40px));min-height:calc(100dvh - 150px);margin:auto;padding:50px 0}.error-scene__copy{position:relative;z-index:2;max-width:650px}.error-scene__eyebrow{display:flex;align-items:center;gap:10px;color:#df8a82;font-size:13px;font-weight:700;letter-spacing:.04em}.error-scene__eyebrow span{width:32px;height:1px;background:#df5149}
.error-scene__number{display:flex;align-items:center;gap:.02em;margin:12px 0 -6px;color:#f0ece7;font-family:'Yekan Boom','Yekan Plus',sans-serif;font-size:clamp(8rem,17vw,14rem);font-weight:900;line-height:.9;letter-spacing:-.08em;text-shadow:0 8px 60px rgba(0,0,0,.55)}.error-scene__number--latin{font-family:'Plus Jakarta Sans',sans-serif;letter-spacing:-.1em}.error-scene__reel{position:relative;width:.72em;height:.72em;margin-inline:.05em;border:.055em solid #e65d53;border-radius:50%;background:#1a1719;box-shadow:0 0 0 .02em #433033,0 0 60px rgba(230,93,83,.2);animation:reel-spin 18s linear infinite}.error-scene__reel::after{content:'';position:absolute;inset:43%;border-radius:50%;background:#df5149}.error-scene__reel i{position:absolute;left:40%;top:7%;width:20%;height:28%;border-radius:50%;background:#e2d8cf;transform-origin:50% 154%}.error-scene__reel i:nth-child(2){transform:rotate(90deg)}.error-scene__reel i:nth-child(3){transform:rotate(180deg)}.error-scene__reel i:nth-child(4){transform:rotate(270deg)}
.error-scene h1{margin-top:18px;font-size:clamp(1.65rem,3vw,2.6rem);font-weight:900;color:#fff}.error-scene__message{max-width:580px;margin-top:15px;color:#aaa5a5;font-size:15px;line-height:2}.error-scene__actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:30px}
.error-scene__projector{position:relative;height:410px;align-self:center}.error-scene__beam{position:absolute;top:68px;right:46%;width:70vw;height:230px;transform:translateX(98%);clip-path:polygon(0 44%,100% 0,100% 100%,0 56%);background:linear-gradient(90deg,rgba(242,197,127,.14),rgba(242,197,127,0));filter:blur(3px);animation:beam-pulse 4s ease-in-out infinite}.error-scene__machine{position:absolute;left:8%;bottom:20px;width:285px;height:300px;filter:drop-shadow(0 35px 30px rgba(0,0,0,.6))}.error-scene__body{position:absolute;left:45px;bottom:46px;width:188px;height:120px;border:2px solid #665a56;border-radius:18px 24px 12px 12px;background:linear-gradient(145deg,#322f31,#171719);box-shadow:inset 0 1px 0 rgba(255,255,255,.08)}
.error-scene__wheel{position:absolute;z-index:2;width:122px;height:122px;border:7px solid #6b605c;border-radius:50%;background:#171719;animation:reel-spin 12s linear infinite}.error-scene__wheel--one{left:32px;top:24px}.error-scene__wheel--two{left:142px;top:0;animation-direction:reverse;animation-duration:9s}.error-scene__wheel i{position:absolute;left:42%;top:7%;width:16%;height:36%;border-radius:50%;background:#514945;transform-origin:50% 120%}.error-scene__wheel i:nth-child(2){transform:rotate(72deg)}.error-scene__wheel i:nth-child(3){transform:rotate(144deg)}.error-scene__wheel i:nth-child(4){transform:rotate(216deg)}.error-scene__wheel i:nth-child(5){transform:rotate(288deg)}.error-scene__lens{position:absolute;z-index:3;right:22px;bottom:100px;width:46px;height:48px;border:5px solid #625754;border-radius:5px 50% 50% 5px;background:#d89358;box-shadow:10px 0 30px rgba(230,158,91,.35)}.error-scene__leg{position:absolute;left:128px;bottom:0;width:24px;height:58px;background:#292629;transform:perspective(40px) rotateX(-8deg)}
.error-scene__footer{position:absolute;bottom:24px;left:0;right:0;text-align:center;color:#656164;font-size:12px}.error-scene__footer span{margin:0 8px;color:#b64a45}@keyframes reel-spin{to{transform:rotate(360deg)}}@keyframes beam-pulse{50%{opacity:.55}}
@media(max-width:800px){.error-scene__header{width:min(100% - 28px,600px)}.error-scene__ticket{padding:7px 10px}.error-scene__stage{display:block;width:min(100% - 36px,600px);min-height:auto;padding:68px 0 130px;text-align:center}.error-scene__copy{margin:auto}.error-scene__eyebrow,.error-scene__actions{justify-content:center}.error-scene__number{justify-content:center;font-size:clamp(7.5rem,40vw,11rem)}.error-scene__message{font-size:14px}.error-scene__projector{display:none}.error-scene__actions>*{flex:1;min-width:190px}}@media(prefers-reduced-motion:reduce){.error-scene__reel,.error-scene__wheel,.error-scene__beam{animation:none}}
</style>

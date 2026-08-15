<script setup lang="ts">
const route = useRoute()

useSeoMeta({ title: String(route.params.username) })
</script>

<template>
  <div class="cinema-page page-section">
    <PageHero
      :title="`پروفایل ${String(route.params.username)}`"
      eyebrow="جامعه روایتو"
      description="صفحه عمومی کاربران به‌زودی میزبان فهرست‌های منتخب و نظرهای سینمایی خواهد بود."
      icon="user"
    />
    <EmptyState
      title="این پرده هنوز آماده نمایش نیست"
      description="نمایش عمومی پروفایل، فهرست‌های منتخب و فعالیت کاربران در نسخه بعدی فعال می‌شود."
      icon="users"
      action-label="بازگشت به خانه"
      action-href="/"
    />
  </div>
</template>

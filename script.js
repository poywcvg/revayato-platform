"use strict";

/**
 * پس از آماده شدن بک‌اند، آدرس‌های API را در این بخش تغییر دهید.
 * فرم‌ها فعلاً نمایشی هستند و درخواست شبکه ارسال نمی‌کنند.
 */
const AUTH_CONFIG = Object.freeze({
  loginEndpoint: "/api/auth/login",
  registerEndpoint: "/api/auth/register",
  googleEndpoint: "/api/auth/google",
});

const card = document.querySelector("#authCard");
const signinPane = document.querySelector("#signinPane");
const signupPane = document.querySelector("#signupPane");
const registerInvite = document.querySelector("#registerInvite");
const loginInvite = document.querySelector("#loginInvite");
const loginForm = document.querySelector("#loginForm");
const registerForm = document.querySelector("#registerForm");
const loginStatus = document.querySelector("#loginStatus");
const registerStatus = document.querySelector("#registerStatus");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

let activeMode = "login";
let focusTimer;

/**
 * تغییر حالت اصلی:
 * فقط data-mode تغییر می‌کند و CSS حرکت پنل، محوشدن متن و جابه‌جایی فرم‌ها را
 * هم‌زمان و بدون display ناگهانی اجرا می‌کند.
 */
function setMode(mode, shouldFocus = true) {
  if (mode !== "login" && mode !== "register") return;

  activeMode = mode;
  card.dataset.mode = mode;

  const isLogin = mode === "login";

  signinPane.toggleAttribute("inert", !isLogin);
  signupPane.toggleAttribute("inert", isLogin);
  signinPane.setAttribute("aria-hidden", String(!isLogin));
  signupPane.setAttribute("aria-hidden", String(isLogin));
  registerInvite.setAttribute("aria-hidden", String(!isLogin));
  loginInvite.setAttribute("aria-hidden", String(isLogin));

  document.title = isLogin ? "ورود | روایتو" : "ثبت‌نام | روایتو";
  card.setAttribute(
    "aria-label",
    isLogin ? "فرم ورود به حساب کاربری" : "فرم ساخت حساب کاربری",
  );

  clearStatus(loginStatus);
  clearStatus(registerStatus);
  clearValidation(isLogin ? registerForm : loginForm);

  if (!shouldFocus) return;

  window.clearTimeout(focusTimer);
  const focusDelay = reducedMotion.matches ? 0 : 740;
  focusTimer = window.setTimeout(() => {
    const target = isLogin
      ? document.querySelector("#loginIdentifier")
      : document.querySelector("#fullName");
    target?.focus({ preventScroll: true });
  }, focusDelay);
}

document.querySelectorAll("[data-switch]").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.switch));
});

/* نمایش و پنهان‌سازی رمز عبور */
document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input) return;

    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    button.classList.toggle("is-visible", showPassword);
    button.setAttribute(
      "aria-label",
      showPassword ? "پنهان کردن رمز عبور" : "نمایش رمز عبور",
    );
    button.setAttribute(
      "title",
      showPassword ? "پنهان کردن رمز عبور" : "نمایش رمز عبور",
    );
    input.focus({ preventScroll: true });
  });
});

function getFieldElement(input) {
  return input?.closest("[data-field]");
}

function markInvalid(input) {
  const field = getFieldElement(input);
  field?.classList.add("has-error");
  input?.setAttribute("aria-invalid", "true");
}

function clearInputValidation(input) {
  const field = getFieldElement(input);
  field?.classList.remove("has-error");
  input?.removeAttribute("aria-invalid");
}

function clearValidation(form) {
  form.querySelectorAll("[aria-invalid]").forEach((input) => {
    input.removeAttribute("aria-invalid");
  });
  form.querySelectorAll(".has-error").forEach((field) => {
    field.classList.remove("has-error");
  });
}

function showStatus(element, message, type = "error") {
  element.textContent = message;
  element.classList.toggle("is-success", type === "success");
}

function clearStatus(element) {
  element.textContent = "";
  element.classList.remove("is-success");
}

function focusFirstInvalid(inputs) {
  const firstInvalid = inputs.find(Boolean);
  firstInvalid?.focus({ preventScroll: false });
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/u.test(value);
}

function validateLogin() {
  const identifier = document.querySelector("#loginIdentifier");
  const password = document.querySelector("#loginPassword");
  const invalidInputs = [];
  let message = "";

  clearValidation(loginForm);
  clearStatus(loginStatus);

  if (identifier.value.trim().length < 3) {
    markInvalid(identifier);
    invalidInputs.push(identifier);
    message = "ایمیل یا نام کاربری معتبر وارد کنید.";
  }

  if (password.value.length < 8) {
    markInvalid(password);
    invalidInputs.push(password);
    if (!message) message = "رمز عبور باید حداقل ۸ کاراکتر داشته باشد.";
  }

  if (message) {
    showStatus(loginStatus, message);
    focusFirstInvalid(invalidInputs);
    return false;
  }

  return true;
}

function validateRegister() {
  const fullName = document.querySelector("#fullName");
  const email = document.querySelector("#registerEmail");
  const password = document.querySelector("#registerPassword");
  const confirmation = document.querySelector("#confirmPassword");
  const terms = document.querySelector("#terms");
  const invalidInputs = [];
  let message = "";

  clearValidation(registerForm);
  clearStatus(registerStatus);

  if (fullName.value.trim().length < 3) {
    markInvalid(fullName);
    invalidInputs.push(fullName);
    message = "نام و نام خانوادگی خود را کامل وارد کنید.";
  }

  if (!isValidEmail(email.value.trim())) {
    markInvalid(email);
    invalidInputs.push(email);
    if (!message) message = "یک ایمیل معتبر وارد کنید.";
  }

  if (password.value.length < 8) {
    markInvalid(password);
    invalidInputs.push(password);
    if (!message) message = "رمز عبور باید حداقل ۸ کاراکتر داشته باشد.";
  }

  if (confirmation.value !== password.value || !confirmation.value) {
    markInvalid(confirmation);
    invalidInputs.push(confirmation);
    if (!message) message = "تکرار رمز عبور با رمز عبور یکسان نیست.";
  }

  if (!terms.checked) {
    markInvalid(terms);
    invalidInputs.push(terms);
    if (!message) message = "برای ادامه، قوانین و حریم خصوصی را بپذیرید.";
  }

  if (message) {
    showStatus(registerStatus, message);
    focusFirstInvalid(invalidInputs);
    return false;
  }

  return true;
}

async function simulateSubmission(form, statusElement, successMessage) {
  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  submitButton.classList.add("is-loading");
  submitButton.setAttribute("aria-busy", "true");

  const delay = reducedMotion.matches ? 80 : 720;
  await new Promise((resolve) => window.setTimeout(resolve, delay));

  submitButton.disabled = false;
  submitButton.classList.remove("is-loading");
  submitButton.removeAttribute("aria-busy");
  showStatus(statusElement, successMessage, "success");
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateLogin()) return;

  const identifier = document.querySelector("#loginIdentifier").value.trim();
  const remember = document.querySelector("#rememberMe").checked;

  try {
    if (remember) {
      localStorage.setItem("revayato-remembered-identifier", identifier);
    } else {
      localStorage.removeItem("revayato-remembered-identifier");
    }
  } catch {
    // محدود بودن localStorage مانع ورود نمایشی نمی‌شود.
  }

  await simulateSubmission(
    loginForm,
    loginStatus,
    "اطلاعات معتبر است؛ اتصال به سرور هنوز فعال نشده.",
  );

  // نمونه اتصال واقعی:
  // await fetch(AUTH_CONFIG.loginEndpoint, { method: "POST", body: new FormData(loginForm) });
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateRegister()) return;

  await simulateSubmission(
    registerForm,
    registerStatus,
    "حساب آمادهٔ ساخت است؛ اتصال به سرور هنوز فعال نشده.",
  );

  // نمونه اتصال واقعی:
  // await fetch(AUTH_CONFIG.registerEndpoint, { method: "POST", body: new FormData(registerForm) });
});

/* خطای هر فیلد به محض اصلاح ورودی پاک می‌شود. */
document.querySelectorAll("input").forEach((input) => {
  const eventName = input.type === "checkbox" ? "change" : "input";
  input.addEventListener(eventName, () => {
    clearInputValidation(input);
    const status = input.closest("form")?.querySelector(".form-status");
    if (status && !status.classList.contains("is-success")) clearStatus(status);
  });
});

document.querySelectorAll("[data-google]").forEach((button) => {
  button.addEventListener("click", () => {
    const status = button.closest("form")?.querySelector(".form-status");
    if (!status) return;
    showStatus(
      status,
      "ورود با گوگل در نسخهٔ نمایشی فعال نیست.",
    );
  });
});

document.querySelector("#forgotPassword").addEventListener("click", (event) => {
  event.preventDefault();
  showStatus(
    loginStatus,
    "بازیابی رمز عبور پس از اتصال به سرور فعال می‌شود.",
  );
});

document.querySelectorAll("[data-policy]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    showStatus(
      registerStatus,
      "صفحهٔ قوانین و حریم خصوصی در نسخهٔ نمایشی قرار نگرفته است.",
    );
  });
});

/* بازیابی شناسه در صورت انتخاب «مرا به خاطر بسپار» */
try {
  const rememberedIdentifier = localStorage.getItem(
    "revayato-remembered-identifier",
  );
  if (rememberedIdentifier) {
    document.querySelector("#loginIdentifier").value = rememberedIdentifier;
    document.querySelector("#rememberMe").checked = true;
  }
} catch {
  // در مرورگرهای محدود، فرم بدون ذخیره محلی کار می‌کند.
}

setMode(activeMode, false);

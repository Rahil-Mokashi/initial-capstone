// The sign-in screen's own language switch (English / Hindi), remembered per terminal. Like Qt, it covers
// this one screen only; the rest of the app is English.
export type LoginLocale = 'en' | 'hi';

export const STRINGS = {
  en: {
    welcomeBack: 'Welcome back',
    usernameLabel: 'Username',
    usernamePlaceholder: 'Enter your username',
    passwordLabel: 'Password',
    pinLabel: 'PIN',
    passwordPlaceholder: 'Your password',
    pinPlaceholder: '6-digit PIN',
    signIn: 'Sign In →',
    signingIn: 'Signing in…',
    usePinInstead: 'Use PIN instead',
    usePasswordInstead: 'Use password instead',
    cantSignIn: "Can't sign in? Ask the person who manages this computer for help.",
    forgotPassword: 'Forgot password?',
    show: 'Show',
    hide: 'Hide',
    usernameRequired: 'Username is required.',
    passwordRequired: 'Password is required.',
    pinRequired: 'PIN is required.',
    capsLockOn: 'Caps Lock is on.',
  },
  hi: {
    welcomeBack: 'वापसी पर स्वागत है',
    usernameLabel: 'उपयोगकर्ता नाम',
    usernamePlaceholder: 'अपना उपयोगकर्ता नाम डालें',
    passwordLabel: 'पासवर्ड',
    pinLabel: 'पिन',
    passwordPlaceholder: 'अपना पासवर्ड डालें',
    pinPlaceholder: '6 अंकों का पिन',
    signIn: 'साइन इन करें →',
    signingIn: 'साइन इन हो रहा है…',
    usePinInstead: 'इसके बजाय पिन का उपयोग करें',
    usePasswordInstead: 'इसके बजाय पासवर्ड का उपयोग करें',
    cantSignIn: 'साइन इन नहीं कर पा रहे? इस कंप्यूटर का प्रबंधन करने वाले व्यक्ति से मदद लें।',
    forgotPassword: 'पासवर्ड भूल गए?',
    show: 'दिखाएं',
    hide: 'छुपाएं',
    usernameRequired: 'उपयोगकर्ता नाम आवश्यक है।',
    passwordRequired: 'पासवर्ड आवश्यक है।',
    pinRequired: 'पिन आवश्यक है।',
    capsLockOn: 'कैप्स लॉक ऑन है।',
  },
} as const;

const LOCALE_KEY = 'pperp.loginLocale';
const RECENT_KEY = 'pperp.recentUsernames';
const RECENT_MAX = 5;

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // storage unavailable: the choice lasts until the window closes
  }
}

export const getLoginLocale = (): LoginLocale => (read(LOCALE_KEY) === 'hi' ? 'hi' : 'en');
export const setLoginLocale = (l: LoginLocale): void => write(LOCALE_KEY, l);

/** This terminal's last few successfully-used usernames, newest first. */
export function getRecentUsernames(): string[] {
  try {
    const parsed: unknown = JSON.parse(read(RECENT_KEY) ?? '[]');
    return Array.isArray(parsed)
      ? parsed.filter((x): x is string => typeof x === 'string').slice(0, RECENT_MAX)
      : [];
  } catch {
    return [];
  }
}
export function recordRecentUsername(name: string): void {
  const next = [
    name,
    ...getRecentUsernames().filter((n) => n.toLowerCase() !== name.toLowerCase()),
  ].slice(0, RECENT_MAX);
  write(RECENT_KEY, JSON.stringify(next));
}

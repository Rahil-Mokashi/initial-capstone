import type { KeyboardEvent } from 'react';

const FIELD = 'input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea';

/**
 * Same behaviour as the Qt app's chain_enter_to_next_field (app/ui/qt_utils.py): in a form,
 * Enter moves to the NEXT field, and only Enter in the LAST field submits. Without this a
 * browser submits the half-filled form on the first Enter (a user-reported problem in Qt).
 * Attach to a <form>: onKeyDown={enterToAdvance}. Multi-line text areas keep Enter as a newline.
 */
export function enterToAdvance(event: KeyboardEvent<HTMLFormElement>): void {
  if (
    event.key !== 'Enter' ||
    event.shiftKey ||
    event.ctrlKey ||
    event.altKey ||
    event.nativeEvent.isComposing
  ) {
    return;
  }
  const target = event.target as HTMLElement;
  if (target.tagName === 'TEXTAREA' || target.tagName === 'BUTTON' || target.tagName === 'A')
    return;
  if (!target.matches(FIELD)) return;

  const form = event.currentTarget;
  const fields = Array.from(form.querySelectorAll<HTMLElement>(FIELD)).filter(
    (el) => !el.hasAttribute('disabled') && el.tabIndex >= 0 && !el.closest('[hidden]'),
  );
  const next = fields[fields.indexOf(target) + 1];
  event.preventDefault();
  if (next) {
    next.focus();
    if (next instanceof HTMLInputElement) next.select();
  } else {
    form.requestSubmit();
  }
}

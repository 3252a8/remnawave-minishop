import type { Attachment } from "svelte/attachments";

// The user name is the keyboard action. A click on the surrounding row or card
// also opens it, without absorbing clicks on the selection control.
export function openUserOnClick(open: () => void): Attachment<HTMLElement> {
  return (element) => {
    function handleClick(event: MouseEvent) {
      if (
        event.defaultPrevented ||
        !(event.target instanceof Element) ||
        event.target.closest("button, a, .user-select-cell")
      ) {
        return;
      }
      open();
    }

    element.addEventListener("click", handleClick);
    return () => element.removeEventListener("click", handleClick);
  };
}

// <button data-copy="#input-id"> copies that input's value to the clipboard.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  const input = document.querySelector(button.dataset.copy);
  if (!input) return;
  const original = button.innerHTML; // our own static markup
  try {
    await navigator.clipboard.writeText(input.value);
    button.textContent = "Copied!";
  } catch (e) {
    input.select(); // fall back to letting the user press Ctrl+C
    button.textContent = "Press Ctrl+C";
  }
  setTimeout(() => { button.innerHTML = original; }, 1500);
});

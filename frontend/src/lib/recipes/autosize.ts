// A text box that grows with what is typed, so a long name wraps and is never cut off.
// (Height is set through the style object, which the strict CSP allows.)

export function autosize(box: HTMLTextAreaElement, _value?: string) {
  void _value;
  const fit = () => {
    box.style.height = 'auto';
    box.style.height = `${box.scrollHeight + 2}px`;
  };
  fit();
  box.addEventListener('input', fit);
  const resize = new ResizeObserver(fit);
  resize.observe(box);
  return {
    update: fit,
    destroy() {
      box.removeEventListener('input', fit);
      resize.disconnect();
    }
  };
}

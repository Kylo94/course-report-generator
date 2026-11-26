document.querySelectorAll('.copy').forEach((button) => {
  button.addEventListener('click', async () => {
    const block = button.closest('.code-block');
    const code = block && block.querySelector('code');
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code.textContent.trim());
      button.textContent = '已复制';
      button.classList.add('done');
      setTimeout(() => {
        button.textContent = '复制';
        button.classList.remove('done');
      }, 1600);
    } catch (error) {
      button.textContent = '复制失败';
      setTimeout(() => { button.textContent = '复制'; }, 1600);
    }
  });
});

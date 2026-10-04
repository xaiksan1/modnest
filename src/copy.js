for (const button of document.querySelectorAll('button.copy')) {
  button.addEventListener('click', async () => {
    const text = button.dataset.copy
    try {
      await navigator.clipboard.writeText(text)
      button.textContent = 'Copied'
    } catch {
      button.textContent = 'Select and copy'
    }
    setTimeout(() => { button.textContent = 'Copy' }, 1800)
  })
}

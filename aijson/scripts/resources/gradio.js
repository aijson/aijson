function main() {
  const onInputKeyDown = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.code === "KeyC") {
      navigator.clipboard.writeText(window.getSelection().toString()).then(() => { });
    } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyX") {
      const newText = window.getSelection().toString();
      if (newText) {
        navigator.clipboard.writeText(newText).then(() => { });
        if (document.activeElement) {
          document.activeElement.value = document.activeElement.value.substring(0, document.activeElement.selectionStart) + activeElement.value.substring(document.activeElement.selectionEnd);
        }
      }
    } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyV") {

      navigator.clipboard.readText().then((textValue) => {
        if (document.activeElement) {
          if (document.activeElement.value) {
            activeElement.setRangeText(textValue,
              document.activeElement.selectionStart,
              document.activeElement.selectionEnd,
              'end');
          }
        }
      });
    } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyA") {
      if (document.activeElement) {
        if (document.activeElement.value) {
          document.activeElement.select();
        }
        else {
          let range = document.createRange().selectNodeContents(document.body)
          window.getSelection().removeAllRanges();
          window.getSelection().addRange(range);
        }
      }
    }
  }
  window.addEventListener('keydown', (e) => {
    onInputKeyDown(e);
  })

  return "";
}

function main() {
    const onInputKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.code === "KeyC") {
        document.execCommand("copy");
      } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyX") {
        document.execCommand("cut");
      } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyV") {
        document.execCommand("paste");
      } else if ((event.ctrlKey || event.metaKey) && event.code === "KeyA") {
        document.execCommand("selectAll");
      }
    }
      window.addEventListener('keydown', (e) => {
        onInputKeyDown(e);
      })

    return "";
}
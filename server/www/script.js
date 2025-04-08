document.addEventListener("DOMContentLoaded", () => {
  const glitchText = document.getElementById('glitch');
  const glitchTextContent = glitchText.textContent;
  
  // Function to create random glitch effect on text
  function randomizeText() {
      let randomText = glitchTextContent.split('').map(char => {
          // Randomly convert characters to numbers or symbols to mimic a glitch
          return Math.random() < 0.1 ? String.fromCharCode(Math.floor(Math.random() * 94) + 33) : char;
      }).join('');
      
      glitchText.textContent = randomText;
  }

  setInterval(randomizeText, 150);
});

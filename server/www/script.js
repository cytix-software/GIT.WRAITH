document.addEventListener("DOMContentLoaded", () => {
  const glitchText = document.getElementById("glitch");
  const glitchTextContent = glitchText.textContent;

  // Function to create random glitch effect on text
  function randomizeText() {
    let randomText = glitchTextContent
      .split("")
      .map((char) => {
        // Randomly convert characters to numbers or symbols to mimic a glitch
        return Math.random() < 0.1
          ? String.fromCharCode(Math.floor(Math.random() * 94) + 33)
          : char;
      })
      .join("");

    glitchText.textContent = randomText;
  }

  setInterval(randomizeText, 200);
});

const demoButton = document.getElementById("demo-btn");
const gitURL = document.getElementById("git-url");

// Send github URL to Wraith server when demo button clicked
demoButton.addEventListener("click", async (e) => {
  if (!gitURL.value) return;

  // Make a loading animation appear or inform the user stuff is happening

  const res = await fetch("/api/scan?repo_url=" + gitURL.value);

  if (!res.ok) {
    return error(`Request failed: ${res.status} ${res.statusText}`);
  }

  let out;
  try {
    out = await res.json();
  } catch {
    return error("Failed to parse JSON data.");
  }

  demoOutput(out.files);
});

const outputBox = document.getElementById("demo-success");

/** Make the demo output box visible and enter markdown into it */
function demoOutput(files) {
  outputBox.style.display = "block";
  outputBox.style.color = "#66ff66";

  let url;
  try {
    url = new URL(gitURL.value);
  } catch {
    return error(`<p>Failed to generate results - Given URL is not valid.</p>`);
  }

  // Convert the markdown to HTML using `marked`
  const htmlContent = files.reduce(
    (str, [fileName, content]) =>
      (str += `<div class="file-box">
    <div class="file-title">${fileName}</div>
    <div class="file-description">${marked.parse(content)}</div>
  </div>`),
    ""
  );

  outputBox.innerHTML =
    `<p><strong>Analysis Results for Repository: <span>${url.pathname.slice(
      1
    )}</span></strong></p>` +
    `<a href="./diagram" target="_blank" class="diagram-link">
  <iframe src="./diagram" class="diagram-iframe" title="System Diagram"></iframe>
</a>` +
    htmlContent;
}

/** Display an error in the output box */
function error(message) {
  outputBox.style.display = "block";
  outputBox.style.color = "red";

  outputBox.innerHTML = `<p>${message}</p>`;
}

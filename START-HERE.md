# Run J.A.R.V.I.S. on your computer

This download contains the backend and interface. No API keys, conversations,
cloud virtual environment, or personal configuration are included.

1. Install **Python 3.12 or newer** from https://www.python.org/downloads/.
   On Windows, enable **Add Python to PATH**. Include Tcl/Tk (the launcher uses it).
2. Extract the ZIP into a folder you own, such as Documents/Jarvis. Do not run
   it inside the ZIP viewer.
3. On macOS, double-click **Start Jarvis.command**. If macOS blocks opening it,
   open Terminal, type `bash ` (with a space), drag **Start Jarvis.command** into
   Terminal, then press Return. On Windows use **Start Jarvis.cmd**; on Linux,
   run `bash start-jarvis.sh` from the extracted folder.
4. Enter your Groq key in the launcher's masked input and click **Start J.A.R.V.I.S.**
   The launcher saves it in an untracked `.env`, installs locked dependencies,
   starts the server on this computer, and opens your browser.
5. Click **Copy access token** in the launcher. In the browser, click **⚙**, paste
   that token, and click **Connect**. Start typing.

Keep the launcher open while using the assistant. Closing it stops the server.
Later launches reuse your private configuration; the Groq input can be left blank.
The access token is copied only when you press the copy button. Avoid pasting it
elsewhere. Provider keys stay in the local `.env`; never share that file.
On Windows, keep the extracted folder in your private user profile and restrict
its access using Windows file permissions if the computer is shared.

The interface runs on your computer and listens only on loopback. There is no
public website, subscription hosting, or port forwarding. **Groq inference still
requires internet access and may use your provider quota.** Prompts and recent
conversation context are sent to Groq. SQLite conversations live in `data/`.
Voice is not implemented yet; the Fish Audio key is not needed for text chat.

If Python cannot be found, finish its installation and restart the launcher.
On Linux, install your distribution's Tk package for your Python version.
If port 8000 is busy, stop the other JARVIS launcher or service before retrying.
First-time installation needs access to Python package registries. No TLS or
package verification is disabled by the launcher.

This is source code with a launcher, not a standalone Windows EXE or macOS app.
It has been tested in the cloud environment; your computer's setup is verified
when you complete the installation and connect successfully.

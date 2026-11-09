import { unlockAccount } from "../api/auth.js";
import { ApiError } from "../api/client.js";

const statusRegion = document.querySelector("#unlock-status");
const heading = document.querySelector("#unlock-title");
const description = document.querySelector("#unlock-description");
const query = new URLSearchParams(location.search);
const token = query.get("token");

history.replaceState(null, "", location.pathname);

if (!token) {
  showFailure("Посилання для розблокування недійсне або застаріле.");
} else {
  unlockAccount(token)
    .then(() => {
      heading.textContent = "Обліковий запис розблоковано";
      description.textContent =
        "Тепер ви можете увійти до NoteLy.";
      statusRegion.textContent = "Розблокування виконано.";
      statusRegion.classList.remove("alert--error");
      statusRegion.classList.add("alert--success");
      statusRegion.hidden = false;
    })
    .catch((error) => {
      const message =
        error instanceof ApiError
          ? error.message
          : "Не вдалося розблокувати обліковий запис. Спробуйте ще раз.";
      showFailure(message);
    });
}

function showFailure(message) {
  heading.textContent = "Не вдалося розблокувати обліковий запис";
  description.textContent = message;
  statusRegion.textContent = message;
  statusRegion.classList.remove("alert--success");
  statusRegion.classList.add("alert--error");
  statusRegion.hidden = false;
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/

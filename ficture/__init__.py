import logging
import matplotlib
matplotlib.use("Agg") # To be save since we don't need interactive visualization

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s:%(levelname)s: %(message)s", "%I:%M:%S %p")
handler.setFormatter(formatter)
logger.addHandler(handler)

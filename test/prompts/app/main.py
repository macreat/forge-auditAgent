# Main application file
from api.local import checkHardware, listAvailableModels, listAvailableQuantizations, downloadSelectedModel
from config.paths import debugPaths

INITIAL_WARNING = "WARNING: While using this application, close all the other appplications to avoid RAM and VRAM filling up. This application is resource intensive and may cause your system to become unresponsive if other applications are running."

if __name__ == "__main__":
	#debugPaths()
	#print(INITIAL_WARNING)
	hardwareResult = checkHardware()
	print("--- Hardware Check ---")
	print(hardwareResult)
	availableModels = listAvailableModels(hardwareResult)
	print("--- Available Models ---")
	for index, model in enumerate(availableModels):
		print(f"[{index}] {model}")

	choice = int(input("\nEnter the number of the model you want to download: "))
	selectedModel = availableModels[choice]

	quantizations = listAvailableQuantizations(selectedModel)
	print(f"\n--- Available Quantizations for {selectedModel} ---")
	quantNames = list(quantizations.keys())
	for i, name in enumerate(quantNames):
		print(f"[{i}] {name} ({quantizations[name]} MB)")

	quantChoice = int(input("\nEnter the number of the quantization: "))
	selectedQuant = quantNames[quantChoice]

	print(f"\nDownloading {selectedModel} ({selectedQuant})...")
	path = downloadSelectedModel(selectedModel, selectedQuant)
	print(f"\nDownload complete: {path}")
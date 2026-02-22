Given the docs/RESULTS you compiled I need a new prototype:

- new sub-directory "classification" for a short python prototype using the best model for image classification you found
- I want you to pass through all images in test_files and create a test_results directory with the same structure and filenames as the source, so old_image/a.jpg would become old_image/a.[yml,md,txt] (whatever format you think is the best for me to check and then for later if we want to index into a vector database for relevancy search)
- I believe the model, when loaded, should take up most of the GPU, so it will not be possible to paralelize the job, right? just confirming.
- Make sure you make the best strategy, based on the results, to have the best classification possible
- My goal is that if an image has a "girl character" I'd rather have the full "Ranma from Ranma 1/2 series" description. Of it it's receipt from my Bank I want to have the relevant information (dates, money value, etc with accuracy) and later be able to index and search for the content (not relying only on filename and easy file metadata such a mtime)

## THE MAIN APP

- use everything we researched and discovered so far.
- I want a desktop app similar to a file explorer, with thumbnail grid view.
- I will be able to use natural language to query this database (use an LLM)
- When I load the first time, I will do something in the console like `sherlock /mnt/terachad/Dropbox`
- You will have a user centralized database, for example `~/.local/share/frank_sherlock/db`
- This local directory will have 2 things: the classification files following the same path structure of the scanned files from target
- Target (ex. Dropbox) must be considered sensitive information: you will NEVER attemp to overwrite or delete or modify any original files whatsoever, just read them
- Because it's a NAS, I can have very deep directory and file structure, even a recursive find might be slow, so you need to be smart in always caching those out, and next time only try to find files added or modified from the timestamp of the previous scan
- You need to be smart to realize if a directory was just renamed or moved and not re-scan the same files (maybe use a fast file fingerprinting)
- After IA classification, the resulting text file must be used to feed a vector database (not sure which is better, classic elasticsearch? zvec?) - the purpose is to be able to query files by name, date range, and of course, the content (including weights such as the confidence, to be able to sort best candidates)
- the initial version of the desktop application can be very simple, a place to query, a grid to dynamically show results
- generating thumbnails can also be costly, so make smart caches in the .local/share directory as well
- I can use this app in any NAS directory I want, you will smart cache the scanning, and not scan if data is already cached and nothing changes since last scan
- I need a quick way to preview the document (such as pressing space on top of a resulting file)
- for the first version, we don't have to care about manipulating the files found in the query (such as moving or renaming), I will ask to add those after the first version is working
- not sure if we should just go with an Electron app or something like Rust Tauri
- you can assume Ollama installed with service running
- try to make this as isolated and self-contained as possible (maybe distributable as an .AppImage on Linux)

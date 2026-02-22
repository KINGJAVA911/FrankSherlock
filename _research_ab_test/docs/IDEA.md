## Frank Sherlock

The goal of this project is to research the possibilities of using modern LLMs and other open source models trained to classify not only text but also media. For example, there are many tools that can open a .jpg file from an anime and classify it as "young woman in a beach background" or similar. But I do not know if it's possible to narrow down to "it's the character Ranma, from Rumiko Takahashi's Ranma 1/2 TV series, in a bikini in the beach background from the OVA The Battle for Miss Beachsite".

Then we have audio. I'd like to research how we advanced in Shazam like audio recognition. I know there are algorithms to find a "fingerprint" of a song and consult a database (is there open databases?) to know what song is playing from just a few seconds.

For video we have short clips and full movies. Need to research if there are ways to figure out what movie we are dealing with without having to read an entire multi-gigabyte stream. Maybe from the audio strem with a Shazam-like scheme? From a few clips?

I prepared this directory test_files with many examples of media files. I'd like you to do a deep research on the options available to catalog media files like that. If there are many options we might have to A/B test them.

I have an AMD 7850X3D CPU with an RTX 5090 GPU running Arch Linux that we can use. I do not want to use remote OpenRouter or OpenAI APIs. I want the research to focus on open source, self-hosted options to run locally. Because if this experiment goes well, then the next project is to use it to catalog terabytes of files from my home NAS.

But before we tackle that, we need to succeed in the research experiment first. You can suggest small scripts and prototypes for us to build and test different models and approaches. Use open source tools such as imagemagick, ffmpeg to manipulate the media files. The goal is to be able to efficiently catalog those files the best we can.

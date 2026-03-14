"use client";

import { useEffect, useRef, useState } from "react";

type SpeechRecognitionErrorCode =
  | "aborted"
  | "audio-capture"
  | "bad-grammar"
  | "language-not-supported"
  | "network"
  | "no-speech"
  | "not-allowed"
  | "phrases-not-supported"
  | "service-not-allowed";

interface SpeechRecognitionAlternative {
  transcript: string;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  0: SpeechRecognitionAlternative;
}

interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: SpeechRecognitionErrorCode;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onaudiostart: ((event: Event) => void) | null;
  onend: ((event: Event) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onstart: ((event: Event) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionInstance;
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

function toUserMessage(error: SpeechRecognitionErrorCode | "unsupported" | "start-failed") {
  switch (error) {
    case "unsupported":
      return "Speech input is not supported in this browser.";
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone access was denied. Allow microphone permission and try again.";
    case "audio-capture":
      return "No microphone was found. Check your audio input and try again.";
    case "no-speech":
      return "No speech was detected. Try again and speak a little closer to the microphone.";
    case "network":
      return "Speech recognition hit a network issue. Try again.";
    case "language-not-supported":
      return "Speech recognition is unavailable for the selected language.";
    case "aborted":
      return "";
    case "bad-grammar":
    case "phrases-not-supported":
      return "Speech recognition could not process that request. Try again.";
    case "start-failed":
      return "Speech recognition could not start. Try again.";
    default:
      return "Speech recognition failed. Try again.";
  }
}

export interface UseSpeechRecognitionOptions {
  onTranscriptChange: (value: string) => void;
  lang?: string;
}

export function useSpeechRecognition({
  onTranscriptChange,
  lang = "en-US",
}: UseSpeechRecognitionOptions) {
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const finalTranscriptRef = useRef("");
  const lastErrorRef = useRef<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isSupported =
    typeof window !== "undefined" &&
    Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);

  const stopListening = () => {
    recognitionRef.current?.stop();
  };

  const startListening = () => {
    if (typeof window === "undefined") {
      return;
    }

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setError(toUserMessage("unsupported"));
      return;
    }

    recognitionRef.current?.abort();

    const recognition = new Recognition();
    recognition.lang = lang;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    finalTranscriptRef.current = "";
    lastErrorRef.current = null;
    setError(null);
    setIsStarting(true);

    recognition.onstart = () => {
      setIsStarting(false);
      setIsListening(true);
    };

    recognition.onresult = (event) => {
      let nextFinal = finalTranscriptRef.current;
      let nextInterim = "";

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = result[0]?.transcript?.trim() ?? "";
        if (!transcript) {
          continue;
        }
        if (result.isFinal) {
          nextFinal = [nextFinal, transcript].filter(Boolean).join(" ").trim();
        } else {
          nextInterim = transcript;
        }
      }

      finalTranscriptRef.current = nextFinal;
      onTranscriptChange([nextFinal, nextInterim].filter(Boolean).join(" ").trim());
    };

    recognition.onerror = (event) => {
      lastErrorRef.current = event.error;
      setIsStarting(false);
      setIsListening(false);
      const message = toUserMessage(event.error);
      setError(message || null);
    };

    recognition.onend = () => {
      setIsStarting(false);
      setIsListening(false);
      recognitionRef.current = null;

      if (!finalTranscriptRef.current && !lastErrorRef.current) {
        setError(toUserMessage("no-speech"));
      }
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setIsStarting(false);
      setIsListening(false);
      setError(toUserMessage("start-failed"));
    }
  };

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, []);

  let statusLabel = "Use microphone";
  if (!isSupported) {
    statusLabel = "Speech unavailable";
  } else if (isStarting) {
    statusLabel = "Starting microphone";
  } else if (isListening) {
    statusLabel = "Listening";
  }

  return {
    error,
    isListening,
    isStarting,
    isSupported,
    startListening,
    statusLabel,
    stopListening,
  };
}

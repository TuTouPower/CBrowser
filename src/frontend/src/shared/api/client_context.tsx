import { createContext, useContext } from "react";
import { defaultApiClient, type ApiClient } from "./client";

/**
 * The ApiClient for the React tree. AppProviders supplies the instance it
 * was given (tests inject an independent stub per case); the default is the
 * shared production client. Pages and layouts read the client from here
 * instead of importing the singleton, so wiring tests exercise the real
 * components against the ApiClient boundary (A22).
 */
export const ApiClientContext = createContext<ApiClient>(defaultApiClient);

export function useApiClient(): ApiClient {
  return useContext(ApiClientContext);
}

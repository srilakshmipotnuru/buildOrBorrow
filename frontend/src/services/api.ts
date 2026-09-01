import axios from 'axios';
import type { EvaluationRequest, EvaluationResponse } from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function evaluateDependencyOrTask(
  request: EvaluationRequest
): Promise<EvaluationResponse> {
  try {
    const response = await apiClient.post<EvaluationResponse>('/evaluate', request);
    return response.data;
  } catch (error: any) {
    if (axios.isAxiosError(error) && error.response) {
      const detail = error.response.data?.detail || 'An error occurred during evaluation.';
      throw new Error(detail);
    }
    throw new Error(error.message || 'Failed to connect to BuildOrBorrow backend server.');
  }
}

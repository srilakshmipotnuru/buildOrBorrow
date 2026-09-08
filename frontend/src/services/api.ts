import axios from 'axios';
import type { EvaluationRequest, EvaluationResponse } from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000, // 2-minute timeout for pipeline processing
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
    if (axios.isAxiosError(error) && error.code === 'ECONNABORTED') {
      throw new Error('Evaluation request timed out while contacting backend server. Please try again.');
    }
    if (axios.isAxiosError(error) && !error.response) {
      throw new Error('Failed to reach BuildOrBorrow backend server. Network Error or connection blocked.');
    }
    throw new Error(error.message || 'Failed to connect to BuildOrBorrow backend server.');
  }
}


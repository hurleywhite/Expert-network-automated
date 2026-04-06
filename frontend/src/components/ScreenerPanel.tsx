import type { ScreenerQuestion, ScreenerResponse } from '../types';

interface Props {
  expertName: string;
  questions: ScreenerQuestion[];
  responses: Record<string, ScreenerResponse>;
  onClose: () => void;
}

export default function ScreenerPanel({ expertName, questions, responses, onClose }: Props) {
  return (
    <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-white shadow-2xl z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b">
        <h2 className="text-lg font-semibold text-gray-900">Screener Questions</h2>
        <div className="flex items-center gap-3">
          <button className="text-gray-400 hover:text-gray-600 text-sm">Collapse All</button>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      </div>

      {/* Subtitle */}
      <div className="px-6 py-3 border-b bg-gray-50">
        <p className="text-sm text-gray-600"><strong>{expertName}</strong> has indicated the following:</p>
      </div>

      {/* Questions */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {questions.map((q) => {
          const response = responses[q.id];
          return (
            <div key={q.id} className="border-b pb-4">
              {/* Question */}
              <p className="text-sm font-medium text-gray-800 mb-3">{q.question_text}</p>

              {/* Answer display */}
              {response ? (
                <div>
                  {/* If multiple choice, show all options with selected highlighted */}
                  {q.question_type === 'multiple_choice' && q.options.length > 0 ? (
                    <div className="flex flex-wrap gap-2 mb-2">
                      {q.options.map((opt) => (
                        <span
                          key={opt}
                          className={`px-3 py-2 text-xs rounded-lg border ${
                            response.answer === opt
                              ? 'bg-blue-50 border-blue-300 text-blue-700 font-semibold'
                              : 'bg-white border-gray-200 text-gray-500'
                          }`}
                        >
                          {opt}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-700 bg-gray-50 rounded p-3">{response.answer}</p>
                  )}

                  {/* Selected answer label on right */}
                  <div className="flex items-center justify-between mt-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      response.confidence === 'high' ? 'bg-green-50 text-green-600' :
                      response.confidence === 'medium' ? 'bg-yellow-50 text-yellow-600' :
                      'bg-gray-50 text-gray-500'
                    }`}>
                      {response.confidence} confidence
                    </span>
                    <span className="text-sm font-medium text-blue-600">{response.answer}</span>
                  </div>

                  {/* Additional comments / reasoning */}
                  {response.reasoning && (
                    <div className="mt-2">
                      <p className="text-xs text-gray-500 font-medium">Additional Comments:</p>
                      <p className="text-xs text-gray-600 mt-1">{response.reasoning}</p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-gray-400 italic">No response recorded</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

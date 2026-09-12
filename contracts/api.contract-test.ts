import {
  classifyCommonErrorResponse,
  type AiDraft,
  type ClassifiedCommonErrorResponse,
  type CompleteMediaUploadRequest,
  type CompleteMediaUploadResponse,
  type CommonErrorResponse,
  type CreateMediaUploadRequest,
  type CreateMediaUploadResponse,
  type CoreHttpErrorCode,
  type MediaDetailResponse,
  type MediaListResponse,
  type MediaOriginalRequestHeaders,
  type MediaPartUploadResponse,
  type MediaWriteHeaders,
  type OrganizeFailure,
  type OrganizeResponse,
  type OrganizeSuccess,
  type RawCommonErrorResponse,
  type StartMediaRecognitionRequest,
  type StartMediaRecognitionResponse,
} from "./api";

type Expect<Condition extends true> = Condition;
type IsAssignable<From, To> = [From] extends [To] ? true : false;

type OrganizeSuccessBranch = Extract<OrganizeResponse, { ok: true }>;
type OrganizeFailureBranch = Extract<OrganizeResponse, { ok: false }>;

type _SuccessBranchUsesPublishedType = Expect<
  IsAssignable<OrganizeSuccessBranch, OrganizeSuccess>
>;
type _PublishedSuccessFitsResponse = Expect<
  IsAssignable<OrganizeSuccess, OrganizeSuccessBranch>
>;
type _FailureBranchUsesPublishedType = Expect<
  IsAssignable<OrganizeFailureBranch, OrganizeFailure>
>;
type _PublishedFailureFitsResponse = Expect<
  IsAssignable<OrganizeFailure, OrganizeFailureBranch>
>;

/** Consumer example: parsing the body before handling the HTTP status. */
export function describeOrganizeResponse(response: OrganizeResponse): string {
  if (response.ok) {
    const success: OrganizeSuccess = response;
    const output: AiDraft = success.output;
    const aiFailed: false = success.ai_failed;

    // @ts-expect-error A successful response has no 422-only failure reason.
    success.failure_reason;

    return `${output.summary}:${aiFailed}`;
  }

  const failure: OrganizeFailure = response;
  const aiFailed: true = failure.ai_failed;
  const error: "ai_organize_failed" = failure.error;

  // @ts-expect-error A 422 failure must not be consumed as fresh AI output.
  failure.output;

  return `${error}:${aiFailed}:${failure.failure_reason}`;
}

type OrganizeHttpResult =
  | { status: 200; body: OrganizeSuccess }
  | { status: 422; body: OrganizeFailure };

/** Consumer example: the documented HTTP status also narrows the body. */
export function describeOrganizeHttpResult(result: OrganizeHttpResult): string {
  if (result.status === 422) {
    const failure: OrganizeFailure = result.body;
    return `saved=${failure.raw_text_preserved};reason=${failure.failure_reason}`;
  }

  const success: OrganizeSuccess = result.body;
  return `saved=${success.raw_text_preserved};summary=${success.output.summary}`;
}

type KnownErrorBranch = Extract<
  ClassifiedCommonErrorResponse,
  { known_error: true }
>["response"];
type UnknownErrorBranch = Extract<
  ClassifiedCommonErrorResponse,
  { known_error: false }
>["response"];

type _KnownBranchUsesClosedErrorSet = Expect<
  IsAssignable<KnownErrorBranch, CommonErrorResponse>
>;
type _PublishedKnownErrorFitsBranch = Expect<
  IsAssignable<CommonErrorResponse, KnownErrorBranch>
>;
type _UnknownBranchKeepsRawShape = Expect<
  IsAssignable<UnknownErrorBranch, RawCommonErrorResponse>
>;
type _RawShapeFitsUnknownBranch = Expect<
  IsAssignable<RawCommonErrorResponse, UnknownErrorBranch>
>;

const knownErrorExample = {
  ok: false,
  error: "stale_version",
} satisfies CommonErrorResponse<"stale_version">;

const forwardCompatibleErrorExample = {
  ok: false,
  error: "server_added_later",
} satisfies RawCommonErrorResponse;

// @ts-expect-error Unknown future codes are not part of the frozen core set.
const invalidKnownError: CommonErrorResponse = forwardCompatibleErrorExample;

/** Consumer example: classification preserves exhaustive known-code handling. */
export function describeCommonError(response: RawCommonErrorResponse): string {
  const classified = classifyCommonErrorResponse(response);

  if (classified.known_error) {
    const known: CommonErrorResponse = classified.response;
    const code: CoreHttpErrorCode = known.error;
    return `known:${code}:${knownErrorExample.error}`;
  }

  const unknown: RawCommonErrorResponse = classified.response;

  // @ts-expect-error A raw forward-compatible string is not a known core code.
  const code: CoreHttpErrorCode = unknown.error;

  return `unknown:${unknown.error}`;
}

const createMediaUploadRequest = {
  kind: "image",
  content_type: "image/png",
  total_parts: 1,
  expected_size: 24,
  expected_sha256:
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  original_filename: "检查单.png",
} satisfies CreateMediaUploadRequest;

const mediaWriteHeaders = {
  "X-Session-Token": "token-from-health",
  "Idempotency-Key": "caller-generated-uuid",
} satisfies MediaWriteHeaders;

const mediaOriginalHeaders = {
  "X-Session-Token": "token-from-health",
  Range: "bytes=0-1023",
} satisfies MediaOriginalRequestHeaders;

const completeMediaUploadRequest = {} satisfies CompleteMediaUploadRequest;

const startMediaRecognitionRequest = {
  expected_version: 1,
  actor_name: "老人",
} satisfies StartMediaRecognitionRequest;

const invalidCreateMediaUploadRequest: CreateMediaUploadRequest = {
  ...createMediaUploadRequest,
  // @ts-expect-error The metadata-creation call does not carry the binary file.
  file: new Blob(["not-sent-here"]),
};

const invalidCompleteMediaUploadRequest: CompleteMediaUploadRequest = {
  // @ts-expect-error Completion currently accepts a strictly empty JSON object.
  expected_version: 1,
};

type CreateMediaHttpResult =
  | { status: 201; body: CreateMediaUploadResponse & { created: true } }
  | { status: 200; body: CreateMediaUploadResponse & { created: false } };

type UploadPartHttpResult =
  | { status: 201; body: MediaPartUploadResponse & { created: true } }
  | { status: 200; body: MediaPartUploadResponse & { created: false } };

type CompleteMediaHttpResult =
  | { status: 201; body: CompleteMediaUploadResponse & { created: true } }
  | { status: 200; body: CompleteMediaUploadResponse & { created: false } };

type StartRecognitionHttpResult = {
  status: 202;
  body: StartMediaRecognitionResponse;
};

/** Consumer example: first-write and idempotent replay statuses narrow `created`. */
export function describeMediaWriteResult(
  created: CreateMediaHttpResult,
  part: UploadPartHttpResult,
  completed: CompleteMediaHttpResult,
): string {
  const uploadId: string = created.body.upload.upload_id;
  const partIndex: number = part.body.part.index;
  const saved: "saved" = completed.body.media.save_status;
  return `${uploadId}:${partIndex}:${saved}`;
}

/** Consumer example: recognition is accepted first, then observed by polling. */
export function describeMediaRecognition(
  started: StartRecognitionHttpResult,
  detail: MediaDetailResponse,
): string {
  const accepted: true = started.body.accepted;
  const attemptId: string = started.body.attempt_id;
  const status = detail.media.recognition_status;

  if (detail.media.recognition?.is_mock === true) {
    return `${accepted}:${attemptId}:offline_mock:${status}`;
  }
  return `${accepted}:${attemptId}:${status}`;
}

/** Consumer example: list/detail JSON never substitutes for original bytes. */
export function describeMediaReads(
  list: MediaListResponse,
  detail: MediaDetailResponse,
): string {
  const first = list.media[0];
  const mediaId = first?.media_id ?? detail.media.media_id;
  return `${mediaId}:${mediaOriginalHeaders.Range ?? "full"}`;
}

void mediaWriteHeaders;
void completeMediaUploadRequest;
void startMediaRecognitionRequest;
void invalidCreateMediaUploadRequest;
void invalidCompleteMediaUploadRequest;

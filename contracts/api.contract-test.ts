import {
  classifyCommonErrorResponse,
  type AiDraft,
  type ClassifiedCommonErrorResponse,
  type CommonErrorResponse,
  type CoreHttpErrorCode,
  type OrganizeFailure,
  type OrganizeResponse,
  type OrganizeSuccess,
  type RawCommonErrorResponse,
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

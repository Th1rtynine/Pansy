<script setup lang="ts">
/**
 * 设置:外部数据源的凭据与身份。
 *
 * 三个源的顺序是**有意排的**:Hikarinagi 最重(要建应用、填两格、还要登录),所以放最上面;
 * Bangumi 一个令牌就够;VNDB 那一格是可选的(读公开条目根本不要它),所以垫底。
 *
 * 未连接时给出官方凭据入口和输入区；连接后只留账号卡、刷新/重新登录与退出操作。
 * Hikarinagi 的应用凭据与账号会话分开保存，退出账号不会移除应用凭据。
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { settings, sources } from "../api";
import { messageOf, useLoad } from "../useLoad";
import { labelOfSource } from "../sourceNames";
import { Alert, Button, Center, FormField, Heading, Input, Popconfirm, Spinner, Text } from "../ui";
import AccountCard from "../components/AccountCard.vue";
import CredentialGuide from "../components/CredentialGuide.vue";
import FormSection from "../components/FormSection.vue";

const CREDENTIAL_PAGES = {
  hikarinagi: "https://www.hikarinagi.org/developers/console",
  bangumi: "https://next.bgm.tv/demo/access-token",
  vndb: "https://vndb.org/u/tokens",
} as const;

const { data, error: loadError, loading, reload } = useLoad(() => settings.get());

const pageError = ref("");
const notice = ref("");
const tokenCheck = ref<{ ok: boolean; detail: string } | null>(null);
const sourcePriority = ref<string[]>([]);
const savingPriority = ref(false);

watch(
  () => data.value?.source_priority,
  (value) => {
    if (value) sourcePriority.value = [...value];
  },
  { immediate: true },
);

function beginAction() {
  pageError.value = "";
  notice.value = "";
}

// ---- Bangumi --------------------------------------------------------------
const bangumiToken = ref("");
const connectingBangumi = ref(false);
const clearingBangumi = ref(false);
const hasBangumiToken = computed(() => Boolean(data.value?.bangumi_token_set));
const bangumiAccount = computed(() => data.value?.bangumi_account ?? null);
/**
 * 令牌验证过了没有。**这是「收不收起输入框」的唯一依据** —— 后端拿「缓存里有没有那份账号资料」
 * 回答,所以换一枚新令牌时它自己就变回 false,页面不用另记一份状态。
 */
const bangumiVerified = computed(() => Boolean(bangumiAccount.value?.verified));
const bangumiName = computed(
  () => bangumiAccount.value?.nickname || bangumiAccount.value?.name || "",
);
const bangumiNote = computed(() => {
  const account = bangumiAccount.value;
  if (!account) return "";
  return [account.name ? `@${account.name}` : "", account.id ? `ID ${account.id}` : ""]
    .filter(Boolean)
    .join(" · ");
});

async function connectBangumi() {
  connectingBangumi.value = true;
  beginAction();
  tokenCheck.value = null;
  try {
    const replacement = bangumiToken.value.trim();
    if (replacement) {
      await settings.saveToken(replacement);
      bangumiToken.value = "";
    }
    tokenCheck.value = await settings.checkToken();
    await reload({ silent: true });
    if (tokenCheck.value.ok) notice.value = "Bangumi 已连接。";
  } catch (failure) {
    pageError.value = messageOf(failure);
  } finally {
    connectingBangumi.value = false;
  }
}

async function moveSource(index: number, offset: number) {
  const target = index + offset;
  if (target < 0 || target >= sourcePriority.value.length || savingPriority.value) return;
  const previous = [...sourcePriority.value];
  const next = [...previous];
  [next[index], next[target]] = [next[target], next[index]];
  sourcePriority.value = next;
  savingPriority.value = true;
  beginAction();
  try {
    await settings.saveSourcePriority(next);
    notice.value = "导入顺序已更新。";
    await reload({ silent: true });
  } catch (failure) {
    sourcePriority.value = previous;
    pageError.value = messageOf(failure);
  } finally {
    savingPriority.value = false;
  }
}

async function clearBangumi() {
  clearingBangumi.value = true;
  beginAction();
  tokenCheck.value = null;
  try {
    // 只清 Bangumi:走 DELETE /settings 会把 Hikarinagi 的凭据一起删掉。
    await settings.saveToken("");
    notice.value = "已退出 Bangumi 账号。";
    await reload({ silent: true });
  } catch (failure) {
    pageError.value = messageOf(failure);
  } finally {
    clearingBangumi.value = false;
  }
}

// ---- Hikarinagi -----------------------------------------------------------
const hikarinagiCredential = computed(() =>
  data.value?.credentials.find((entry) => entry.source === "hikarinagi"),
);
const credentialsReady = computed(() => Boolean(hikarinagiCredential.value?.configured));
const clientId = ref("");
const clientSecret = ref("");
const savingCredentials = ref(false);
const clearingCredentials = ref(false);
/**
 * 存下的凭据上点「更换」才展开那两格。**与登录状态是两回事**:退出登录只掉会话,凭据还在
 * (后端 `logout()` 不碰它),所以这两格收起来之后,那一行掩码仍然留在页面上。
 */
const credentialsSwapping = ref(false);

const account = computed(() => data.value?.hikarinagi_account ?? null);
const loggedIn = computed(() => Boolean(account.value?.logged_in));
const accountName = computed(
  () => account.value?.nickname || account.value?.name || "Hikarinagi 用户",
);
const accountNote = computed(() => {
  const current = account.value;
  if (!current) return "";
  return [current.name ? `@${current.name}` : "", current.id ? `ID ${current.id}` : ""]
    .filter(Boolean)
    .join(" · ");
});

const callbackUri = computed(() =>
  account.value?.redirect_uri ||
  (typeof window === "undefined"
    ? ""
    : `${window.location.origin}/api/sources/hikarinagi/callback`),
);
const loginScope = computed(
  () => account.value?.login_scope || "openid profile offline_access",
);

async function saveHikarinagiCredentials() {
  savingCredentials.value = true;
  beginAction();
  try {
    await settings.saveCredentials("hikarinagi", {
      client_id: clientId.value,
      client_secret: clientSecret.value,
    });
    clientId.value = "";
    clientSecret.value = "";
    credentialsSwapping.value = false;
    notice.value = "Hikarinagi 凭据已保存。";
    await reload({ silent: true });
  } catch (failure) {
    pageError.value = messageOf(failure);
  } finally {
    savingCredentials.value = false;
  }
}

async function clearHikarinagiCredentials() {
  clearingCredentials.value = true;
  beginAction();
  try {
    await settings.saveCredentials("hikarinagi", { client_id: "", client_secret: "" });
    credentialsSwapping.value = false;
    notice.value = "已移除 Hikarinagi 应用凭据。";
    await reload({ silent: true });
  } catch (failure) {
    pageError.value = messageOf(failure);
  } finally {
    clearingCredentials.value = false;
  }
}

const loggingIn = ref(false);
const loggingOut = ref(false);
const relogging = ref(false);
let waitingForLogin = false;

async function openHikarinagiLogin(popup: Window | null) {
  const answer = await sources.hikarinagiLogin(callbackUri.value);
  if (!answer.url) {
    popup?.close();
    pageError.value = answer.detail || "无法开始登录。";
    return;
  }
  waitingForLogin = true;
  if (popup) popup.location.href = answer.url;
  else window.location.href = answer.url;
}

async function startLogin() {
  loggingIn.value = true;
  beginAction();
  const popup = window.open("", "pansy-hikarinagi-login", "width=520,height=680");
  try {
    await openHikarinagiLogin(popup);
  } catch (failure) {
    popup?.close();
    pageError.value = messageOf(failure);
  } finally {
    loggingIn.value = false;
  }
}

/** 重新走一遍标准授权。弹窗必须在点击时立即创建,否则会被浏览器拦住。 */
async function reloginHikarinagi() {
  relogging.value = true;
  beginAction();
  const popup = window.open("", "pansy-hikarinagi-login", "width=520,height=680");
  try {
    await sources.hikarinagiLogout();
    await openHikarinagiLogin(popup);
  } catch (failure) {
    popup?.close();
    pageError.value = messageOf(failure);
    await reload({ silent: true });
  } finally {
    relogging.value = false;
  }
}

async function refreshAfterLogin() {
  if (!waitingForLogin) return;
  waitingForLogin = false;
  await reload({ silent: true });
}

async function logout() {
  loggingOut.value = true;
  beginAction();
  try {
    await sources.hikarinagiLogout();
    notice.value = "已退出 Hikarinagi 账号。";
    await reload({ silent: true });
  } catch (failure) {
    pageError.value = messageOf(failure);
  } finally {
    loggingOut.value = false;
  }
}

// ---- VNDB -----------------------------------------------------------------
/**
 * VNDB 那一格**是可选的**,这点跟另两个源不一样:**它读公开条目根本不需要令牌**。
 * 令牌只有一个用途 —— 以后读你自己账号的收藏。所以没填、没验证,都不影响 VNDB 能不能用,
 * 页面上也不该说「没有它就用不了」。
 */
const vndbCredential = computed(() => data.value?.credentials.find((entry) => entry.source === "vndb"));
const vndbSaved = computed(() => Boolean(vndbCredential.value?.masked));
const vndbToken = ref("");
const connectingVndb = ref(false);
const clearingVndb = ref(false);
const vndbCheck = ref<{ ok: boolean; detail: string } | null>(null);

const vndbAccount = computed(() => data.value?.vndb_account ?? null);
/** 与 Bangumi 同一套:验过了就收起输入框,直到退出/换账号。 */
const vndbVerified = computed(() => Boolean(vndbAccount.value?.verified));
const vndbName = computed(() => vndbAccount.value?.nickname || vndbAccount.value?.name || "");
const vndbNote = computed(() => {
  const current = vndbAccount.value;
  if (!current) return "";
  return [current.name ? `@${current.name}` : "", current.id ? `u${current.id}` : ""]
    .filter(Boolean)
    .join(" · ");
});

async function connectVndb() {
  connectingVndb.value = true;
  beginAction();
  vndbCheck.value = null;
  try {
    const replacement = vndbToken.value.trim();
    if (replacement) {
      await settings.saveCredentials("vndb", { token: replacement });
      vndbToken.value = "";
    }
    vndbCheck.value = await settings.checkVndbToken();
    await reload({ silent: true });
    if (vndbCheck.value.ok) notice.value = "VNDB 已连接。";
  } catch (failure) {
    pageError.value = messageOf(failure);
  } finally {
    connectingVndb.value = false;
  }
}

async function clearVndb() {
  clearingVndb.value = true;
  beginAction();
  vndbCheck.value = null;
  try {
    await settings.saveCredentials("vndb", { token: "" });
    notice.value = "已退出 VNDB 账号。";
    await reload({ silent: true });
  } catch (failure) {
    pageError.value = messageOf(failure);
  } finally {
    clearingVndb.value = false;
  }
}

// ---- 通用 -----------------------------------------------------------------

const copied = ref("");
async function copy(value: string, key: string) {
  try {
    await navigator.clipboard.writeText(value);
    copied.value = key;
  } catch {
    copied.value = "failed";
  }
  window.setTimeout(() => (copied.value = ""), 1600);
}

onMounted(() => window.addEventListener("focus", refreshAfterLogin));
onUnmounted(() => window.removeEventListener("focus", refreshAfterLogin));
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>
  <Alert v-else-if="loadError" tone="danger" title="无法读取设置">{{ loadError }}</Alert>

  <div v-else-if="data" class="flex flex-col gap-6">
    <div class="flex flex-col gap-1">
      <Heading :level="1" size="xl">设置</Heading>
      <Text size="sm" tone="muted">连接用于检索与导入的外部数据源。</Text>
    </div>

    <Alert v-if="pageError" tone="danger">{{ pageError }}</Alert>
    <Alert v-else-if="notice" tone="success">{{ notice }}</Alert>

    <FormSection title="导入顺序" description="优先采用排在前面的来源，缺少的字段再由下一项补全。">
      <ol class="flex flex-col gap-1.5">
        <li
          v-for="(source, index) in sourcePriority"
          :key="source"
          class="flex items-center gap-3 rounded-control border border-line bg-surface px-3 py-2"
        >
          <span class="flex size-6 shrink-0 items-center justify-center rounded-full bg-inset text-xs text-muted">
            {{ index + 1 }}
          </span>
          <Text class="min-w-0 flex-1" weight="medium">{{ labelOfSource(source) }}</Text>
          <div class="flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              :disabled="index === 0 || savingPriority"
              :aria-label="`提高 ${labelOfSource(source)} 的优先级`"
              @click="moveSource(index, -1)"
            >↑</Button>
            <Button
              size="sm"
              variant="ghost"
              :disabled="index === sourcePriority.length - 1 || savingPriority"
              :aria-label="`降低 ${labelOfSource(source)} 的优先级`"
              @click="moveSource(index, 1)"
            >↓</Button>
          </div>
        </li>
      </ol>
      <Text size="xs" tone="faint">作者、别名与标签会合并去重；你手动改过的内容不会被覆盖。</Text>
    </FormSection>

    <!--
      三个源的顺序是**有意排的**:Hikarinagi 最重(要建应用、填两格、还要登录),所以放最上面;
      Bangumi 一个令牌就够;VNDB 那一格是可选的(读公开条目根本不要它),所以垫底。

      未连接时展示官方凭据入口与输入区；连接后收起准备步骤，只展示账号与维护操作。
      Hikarinagi 的应用凭据与账号会话分层保存，退出账号不会移除应用凭据。
    -->
    <FormSection title="Hikarinagi" description="连接后可读取条目并使用账号授权。">
      <!-- 第一层:应用凭据。存下了就只显示掩码(旁边留「更换」),没存才摆输入框。 -->
      <CredentialGuide
        v-if="!loggedIn && !credentialsReady"
        title="获取应用凭据"
        description="前往 Hikarinagi 开发者控制台创建应用，再将凭据填在下方。"
        action="打开开发者控制台"
        :href="CREDENTIAL_PAGES.hikarinagi"
      />

      <div v-if="!loggedIn" class="flex flex-col gap-3 rounded-card border border-line bg-subtle p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex flex-col gap-0.5">
            <Text size="sm" weight="medium">应用接入</Text>
            <Text size="xs" tone="faint">用于发起 Hikarinagi 账号授权</Text>
          </div>
          <div v-if="credentialsReady" class="flex flex-wrap items-center justify-end gap-2">
            <Text size="sm" weight="medium">{{ hikarinagiCredential?.masked }}</Text>
            <Button v-if="!credentialsSwapping" size="sm" @click="credentialsSwapping = true">
              更换凭据
            </Button>
          </div>
          <Text v-else size="sm" tone="faint">尚未配置</Text>
        </div>

        <div v-if="!credentialsReady || credentialsSwapping" class="flex flex-col gap-3 border-t border-line pt-3">
          <div class="grid gap-3 sm:grid-cols-2">
            <FormField label="Client ID">
              <Input v-model="clientId" type="password" placeholder="Client ID" autocomplete="off" />
            </FormField>
            <FormField label="Client Secret">
              <Input v-model="clientSecret" type="password" placeholder="Client Secret" autocomplete="off" />
            </FormField>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <Button
              variant="solid"
              tone="accent"
              :loading="savingCredentials"
              :disabled="!clientId.trim() || !clientSecret.trim()"
              @click="saveHikarinagiCredentials"
            >
              保存凭据
            </Button>
            <Button v-if="credentialsSwapping" @click="credentialsSwapping = false">取消</Button>
            <Button
              v-if="credentialsReady"
              variant="ghost"
              tone="danger"
              :loading="clearingCredentials"
              @click="clearHikarinagiCredentials"
            >
              移除凭据
            </Button>
          </div>
        </div>
      </div>

      <!-- 第二层:登录状态。这一层是唯一会被「退出登录」改掉的东西。 -->
      <template v-if="loggedIn">
        <div class="flex flex-col gap-4 rounded-card border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
          <AccountCard
            :name="accountName"
            source="Hikarinagi"
            :note="accountNote"
            :avatar-url="account?.avatar_url"
            :signature="account?.signature"
            status="已登录"
          />
          <div class="flex shrink-0 self-end flex-wrap items-center justify-end gap-2">
            <Button :loading="relogging" @click="reloginHikarinagi">重新登录</Button>
            <Popconfirm
              title="退出 Hikarinagi？"
              description="应用凭据会保留。"
              confirm-text="退出"
              tone="danger"
              :on-confirm="logout"
            >
              <Button variant="ghost" tone="danger" :loading="loggingOut">退出</Button>
            </Popconfirm>
          </div>
        </div>
      </template>

      <!-- 没登上:登录按钮,以及往控制台抄的那两行(只在凭据还没存时摆出来) -->
      <template v-else>
        <div class="flex flex-wrap items-center gap-3">
          <Button
            variant="solid"
            tone="accent"
            :loading="loggingIn"
            :disabled="!credentialsReady"
            @click="startLogin"
          >
            登录 Hikarinagi
          </Button>
          <Text v-if="!credentialsReady" size="sm" tone="faint">请先完成上方的应用接入。</Text>
        </div>

        <div v-if="!credentialsReady" class="flex flex-col gap-3 rounded-card bg-subtle p-4">
          <Text size="sm" weight="medium">应用控制台需要填写</Text>

          <FormField label="回调地址">
            <div class="flex items-center gap-2">
              <code class="min-w-0 flex-1 break-all font-mono text-sm">{{ callbackUri }}</code>
              <Button size="sm" @click="copy(callbackUri, 'callback')">
                {{ copied === "callback" ? "已复制" : "复制" }}
              </Button>
            </div>
          </FormField>

          <FormField label="权限">
            <div class="flex items-center gap-2">
              <code class="min-w-0 flex-1 break-all font-mono text-sm">{{ loginScope }}</code>
              <Button size="sm" @click="copy(loginScope, 'scope')">
                {{ copied === "scope" ? "已复制" : "复制" }}
              </Button>
            </div>
          </FormField>

          <Text v-if="copied === 'failed'" size="xs" tone="faint">没能复制,手动选一下。</Text>
        </div>
      </template>
    </FormSection>

    <!-- Bangumi:一个访问令牌就够。连接时直接保存并验证。 -->
    <FormSection title="Bangumi" description="用于读取更完整的条目信息。">
      <!-- 验过了:只留账号卡、刷新连接与退出,输入框收起来。 -->
      <template v-if="bangumiVerified">
        <div class="flex flex-col gap-4 rounded-card border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
          <AccountCard
            :name="bangumiName"
            source="Bangumi"
            :note="bangumiNote"
            :avatar-url="bangumiAccount?.avatar_url"
            :signature="bangumiAccount?.signature"
            status="已连接"
          />
          <div class="flex shrink-0 self-end flex-wrap items-center justify-end gap-2">
            <Button :loading="connectingBangumi" @click="connectBangumi">刷新连接</Button>
            <Popconfirm
              v-if="data.bangumi_token_from === 'settings'"
              title="退出 Bangumi？"
              description="当前令牌将被移除。"
              confirm-text="退出"
              tone="danger"
              :on-confirm="clearBangumi"
            >
              <Button variant="ghost" tone="danger" :loading="clearingBangumi">退出</Button>
            </Popconfirm>
          </div>
        </div>
      </template>

      <!-- 没验过:给出官方入口与输入框。 -->
      <template v-else>
        <CredentialGuide
          title="获取访问令牌"
          description="打开 Bangumi 的令牌页面，创建后粘贴到下方。"
          action="打开令牌页面"
          :href="CREDENTIAL_PAGES.bangumi"
        />

        <div class="flex items-baseline justify-between gap-4">
          <Text size="sm" tone="muted">访问令牌</Text>
          <Text v-if="hasBangumiToken" size="sm" weight="medium">{{ data.bangumi_token_masked }}</Text>
          <Text v-else size="sm" tone="faint">未设置</Text>
        </div>

        <FormField>
          <Input v-model="bangumiToken" type="password" placeholder="粘贴访问令牌" autocomplete="off" />
        </FormField>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            variant="solid"
            tone="accent"
            :loading="connectingBangumi"
            :disabled="!bangumiToken.trim() && !hasBangumiToken"
            @click="connectBangumi"
          >
            连接
          </Button>
        </div>

        <Alert v-if="tokenCheck" :tone="tokenCheck.ok ? 'success' : 'warning'">
          {{ tokenCheck.detail }}
        </Alert>
      </template>
    </FormSection>

    <!--
      VNDB:只有一格,而且**是可选的** —— 它读公开条目根本不要令牌。所以这里不写"没有它就用不了"
      那种话,只说明这一格是给什么用的。收起/展开那一套与 Bangumi 完全一致。
    -->
    <FormSection
      title="VNDB"
      description="公开条目无需令牌；账号功能可按需连接。"
    >
      <template v-if="vndbVerified">
        <div class="flex flex-col gap-4 rounded-card border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
          <AccountCard
            :name="vndbName"
            source="VNDB"
            :note="vndbNote"
            :avatar-url="vndbAccount?.avatar_url"
            :signature="vndbAccount?.signature"
            status="已连接"
          />
          <div class="flex shrink-0 self-end flex-wrap items-center justify-end gap-2">
            <Button :loading="connectingVndb" @click="connectVndb">刷新连接</Button>
            <Popconfirm
              title="退出 VNDB？"
              description="当前令牌将被移除。"
              confirm-text="退出"
              tone="danger"
              :on-confirm="clearVndb"
            >
              <Button variant="ghost" tone="danger" :loading="clearingVndb">退出</Button>
            </Popconfirm>
          </div>
        </div>
      </template>

      <template v-else>
        <CredentialGuide
          title="获取 API 令牌"
          description="只使用公开条目时可以跳过；需要账号功能时再创建。"
          action="打开令牌页面"
          :href="CREDENTIAL_PAGES.vndb"
        />

        <div class="flex items-baseline justify-between gap-4">
          <Text size="sm" tone="muted">API 令牌</Text>
          <Text v-if="vndbSaved" size="sm" weight="medium">{{ vndbCredential?.masked }}</Text>
          <Text v-else size="sm" tone="faint">未设置</Text>
        </div>

        <FormField>
          <Input v-model="vndbToken" type="password" placeholder="粘贴 API 令牌" autocomplete="off" />
        </FormField>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            variant="solid"
            tone="accent"
            :loading="connectingVndb"
            :disabled="!vndbToken.trim() && !vndbSaved"
            @click="connectVndb"
          >
            连接
          </Button>
        </div>

        <Alert v-if="vndbCheck" :tone="vndbCheck.ok ? 'success' : 'warning'">
          {{ vndbCheck.detail }}
        </Alert>

      </template>
    </FormSection>
  </div>
</template>

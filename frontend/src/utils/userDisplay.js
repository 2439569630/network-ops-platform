const normalizeText = (value) => {
  if (value === null || value === undefined) return '';
  return String(value).trim();
};

export const getUserDisplayName = (userLike, fallback = '-') => {
  if (!userLike) return fallback;

  const displayName = normalizeText(userLike.display_name || userLike.displayName);
  if (displayName) return displayName;

  const nickname = normalizeText(userLike.nickname || userLike.nickName);
  if (nickname) return nickname;

  const username = normalizeText(userLike.username || userLike.userName);
  if (username) return username;

  const name = normalizeText(userLike.name);
  if (name) return name;

  return fallback;
};

export const formatUserDisplay = (userLike, options = {}) => {
  const {
    fallback = '-',
    showUsernameWhenDifferent = false,
    includeIdWhenMissingName = false,
  } = options;

  if (!userLike) return fallback;

  const nickname = normalizeText(userLike.nickname || userLike.nickName || userLike.display_name || userLike.displayName || userLike.name);
  const username = normalizeText(userLike.username || userLike.userName);

  if (nickname && username && showUsernameWhenDifferent && nickname !== username) {
    return `${nickname} (${username})`;
  }
  if (nickname) return nickname;
  if (username) return username;

  if (includeIdWhenMissingName) {
    const id = userLike.id ?? userLike.user_id ?? userLike.target_user_id ?? null;
    if (id !== null && id !== undefined && String(id).trim() !== '') {
      return `用户#${id}`;
    }
  }

  return fallback;
};

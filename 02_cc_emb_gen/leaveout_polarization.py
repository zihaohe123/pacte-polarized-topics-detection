from collections import Counter
import numpy as np
import scipy.sparse as sp
import sys
# from helpers.funcs import *
#
# sno = nltk.stem.SnowballStemmer('english')
#
# config = json.load(open('../config.json', 'r'))
# TWEET_DIR = config['TWEET_DIR']
# OUTPUT_DIR = config['OUTPUT_DIR']

# events = open(INPUT_DIR + 'event_names.txt', 'r').read().splitlines()
#
# parser = argparse.ArgumentParser(description='Computes polarization value between two groups of texts.')
# parser.add_argument('-f','--filtering', help='Kind of data filtering.', default='nofilter')
# parser.add_argument('-c','--cluster', help='Kind of cluster method to filter with (only if filtering is "clustered"', default=None)
# parser.add_argument('-l','--leaveout', help='Whether to use leave-out.', action="store_true")
# parser.add_argument('-m','--method', help='Which method to use: posterior, mutual_information or chi_square', default='posterior')
# parser.add_argument('-b','--between', help='Whether to calculate between-topic polarization.', action="store_true")
# args = vars(parser.parse_args())


# def get_user_token_counts(tweets, vocab):
#     # user-based
#     users = tweets.groupby('user_id')
#     row_idx = []
#     col_idx = []
#     data = []
#     for group_idx, (u, group), in enumerate(users):
#         word_indices = []
#         for split in group['text']:
#             count = 0
#             prev = ''
#             for w in split:
#                 if w == '':
#                     continue
#                 if w in vocab:
#                     word_indices.append(vocab[w])
#                 if count > 0:
#                     bigram = prev + ' ' + w
#                     if bigram in vocab:
#                         word_indices.append(vocab[bigram])
#                 count += 1
#                 prev = w
#         for k, v in Counter(word_indices).items():
#             col_idx.append(group_idx)
#             row_idx.append(k)
#             data.append(v)
#     return sp.csr_matrix((data, (col_idx, row_idx)), shape=(len(users), len(vocab)))


def get_news_token_counts(corpus, idx2word):
    row_idx = []
    col_idx = []
    data = []
    for i, doc in enumerate(corpus):
        for j, count in doc:
            row_idx.append(i)
            col_idx.append(j)
            data.append(count)
    return sp.csr_matrix((data, (row_idx, col_idx)), shape=(len(corpus), len(idx2word)))


# def get_user_topic_counts(tweets):
#     # user-based
#     users = tweets.groupby('user_id')
#     row_idx = []
#     col_idx = []
#     data = []
#     for group_idx, (u, group), in enumerate(users):
#         for k, v in Counter(group['topic']).items():
#             col_idx.append(group_idx)
#             row_idx.append(k)
#             data.append(v)
#     return sp.csr_matrix((data, (col_idx, row_idx)), shape=(len(users), NUM_CLUSTERS))


def get_party_q(party_counts, exclude_user_id = None):
    user_sum = party_counts.sum(axis=0)
    if exclude_user_id:
        user_sum -= party_counts[exclude_user_id, :]
    total_sum = user_sum.sum()
    return user_sum / total_sum


def get_rho(dem_q, rep_q):
    return (rep_q / (dem_q + rep_q)).transpose()


def get_token_user_counts(party_counts):
    no_tokens = party_counts.shape[1]
    nonzero = sp.find(party_counts)[:2]
    user_t_counts = Counter(nonzero[1])  # number of users using each term
    party_t = np.ones(no_tokens)  # add one smoothing
    for k, v in user_t_counts.items():
        party_t[k] += v
    return party_t


def mutual_information(dem_t, rep_t, dem_not_t, rep_not_t, dem_no, rep_no):
    no_users = dem_no + rep_no
    all_t = dem_t + rep_t
    all_not_t = no_users - all_t + 4
    mi_dem_t = dem_t * np.log2(no_users * (dem_t / (all_t * dem_no)))
    mi_dem_not_t = dem_not_t * np.log2(no_users * (dem_not_t / (all_not_t * dem_no)))
    mi_rep_t = rep_t * np.log2(no_users * (rep_t / (all_t * rep_no)))
    mi_rep_not_t = rep_not_t * np.log2(no_users * (rep_not_t / (all_not_t * rep_no)))
    return (1 / no_users * (mi_dem_t + mi_dem_not_t + mi_rep_t + mi_rep_not_t)).transpose()[:, np.newaxis]


def chi_square(dem_t, rep_t, dem_not_t, rep_not_t, dem_no, rep_no):
    no_users = dem_no + rep_no
    all_t = dem_t + rep_t
    all_not_t = no_users - all_t + 4
    chi_enum = no_users * (dem_t * rep_not_t - dem_not_t * rep_t) ** 2
    chi_denom = all_t * all_not_t * (dem_t + dem_not_t) * (rep_t + rep_not_t)
    return (chi_enum / chi_denom).transpose()[:, np.newaxis]


def calculate_polarization(dem_counts, rep_counts, measure="posterior", leaveout=True):
    dem_user_total = dem_counts.sum(axis=1)
    rep_user_total = rep_counts.sum(axis=1)

    dem_user_distr = (sp.diags(1 / dem_user_total.A.ravel())).dot(dem_counts)  # get row-wise distributions
    rep_user_distr = (sp.diags(1 / rep_user_total.A.ravel())).dot(rep_counts)
    dem_no = dem_counts.shape[0]
    rep_no = rep_counts.shape[0]
    assert (set(dem_user_total.nonzero()[0]) == set(range(dem_no)))  # make sure there are no zero rows
    assert (set(rep_user_total.nonzero()[0]) == set(range(rep_no)))  # make sure there are no zero rows
    if measure not in ('posterior', 'mutual_information', 'chi_square'):
        print('invalid method')
        return
    dem_q = get_party_q(dem_counts)
    rep_q = get_party_q(rep_counts)
    dem_t = get_token_user_counts(dem_counts)
    rep_t = get_token_user_counts(rep_counts)
    dem_not_t = dem_no - dem_t + 2  # because of add one smoothing
    rep_not_t = rep_no - rep_t + 2  # because of add one smoothing
    func = mutual_information if measure == 'mutual_information' else chi_square

    # apply measure without leave-out
    if not leaveout:
        if measure == 'posterior':
            token_scores_rep = get_rho(dem_q, rep_q)
            token_scores_dem = 1. - token_scores_rep
        else:
            token_scores_dem = func(dem_t, rep_t, dem_not_t, rep_not_t, dem_no, rep_no)
            token_scores_rep = token_scores_dem
        dem_val = 1 / dem_no * dem_user_distr.dot(token_scores_dem).sum()
        rep_val = 1 / rep_no * rep_user_distr.dot(token_scores_rep).sum()
        return 1/2 * (dem_val + rep_val)

    # apply measures via leave-out
    dem_addup = 0
    rep_addup = 0
    dem_leaveout_no = dem_no - 1
    rep_leaveout_no = rep_no - 1
    for i in range(dem_no):
        if measure == 'posterior':
            dem_leaveout_q = get_party_q(dem_counts, i)
            token_scores_dem = 1. - get_rho(dem_leaveout_q, rep_q)
        else:
            dem_leaveout_t = dem_t.copy()
            excl_user_terms = sp.find(dem_counts[i, :])[1]
            for term_idx in excl_user_terms:
                dem_leaveout_t[term_idx] -= 1
            dem_leaveout_not_t = dem_leaveout_no - dem_leaveout_t + 2
            token_scores_dem = func(dem_leaveout_t, rep_t, dem_leaveout_not_t, rep_not_t, dem_leaveout_no, rep_no)
        dem_addup += dem_user_distr[i, :].dot(token_scores_dem)[0, 0]
    for i in range(rep_no):
        if measure == 'posterior':
            rep_leaveout_q = get_party_q(rep_counts, i)
            token_scores_rep = get_rho(dem_q, rep_leaveout_q)
        else:
            rep_leaveout_t = rep_t.copy()
            excl_user_terms = sp.find(rep_counts[i, :])[1]
            for term_idx in excl_user_terms:
                rep_leaveout_t[term_idx] -= 1
            rep_leaveout_not_t = rep_leaveout_no - rep_leaveout_t + 2
            token_scores_rep = func(dem_t, rep_leaveout_t, dem_not_t, rep_leaveout_not_t, dem_no, rep_leaveout_no)
        rep_addup += rep_user_distr[i, :].dot(token_scores_rep)[0, 0]
    rep_val = 1 / rep_no * rep_addup
    dem_val = 1 / dem_no * dem_addup
    return 1/2 * (dem_val + rep_val)


def get_leaveout_score(corpus1, corpus2, id2word, token_partisanship_measure='posterior',
                       leaveout=True, default_score=0.5, min_docs=10, max_docs=999):
    """
    Measure polarization.
    :param event: name of the event
    :param data: dataframe with 'text' and 'user_id'
    :param token_partisanship_measure: type of measure for calculating token partisanship based on user-token counts
    :param leaveout: whether to use leave-out estimation
    :param between_topic: whether the estimate is between topics or tokens
    :param default_score: default token partisanship score
    :return:
    """
    import gc

    dem_counts = get_news_token_counts(corpus1, id2word)
    rep_counts = get_news_token_counts(corpus2, id2word)

    dem_user_len = dem_counts.shape[0]
    rep_user_len = rep_counts.shape[0]

    # return these values when there is not enough data to make predictions on
    if dem_user_len < min_docs or rep_user_len < min_docs:
        return default_score, default_score, dem_user_len + rep_user_len

    if max_docs < dem_user_len:
        dem_counts = dem_counts[:dem_user_len]
    if max_docs < rep_user_len:
        rep_counts = rep_counts[:rep_user_len]

    import random
    RNG = random.Random()  # make everything reproducible
    RNG.seed(42)
    # make the prior neutral (i.e. make sure there are the same number of Rep and Dem users)
    dem_user_len = dem_counts.shape[0]
    rep_user_len = rep_counts.shape[0]
    if dem_user_len > rep_user_len:
        dem_subset = np.array(RNG.sample(range(dem_user_len), rep_user_len))
        dem_counts = dem_counts[dem_subset, :]
        dem_user_len = dem_counts.shape[0]
    elif rep_user_len > dem_user_len:
        rep_subset = np.array(RNG.sample(range(rep_user_len), dem_user_len))
        rep_counts = rep_counts[rep_subset, :]
        rep_user_len = rep_counts.shape[0]
    assert (dem_user_len == rep_user_len)

    all_counts = sp.vstack([dem_counts, rep_counts])

    wordcounts = all_counts.nonzero()[1]

    # filter words used by fewer than 2 people
    all_counts = all_counts[:, np.array([(np.count_nonzero(wordcounts == i) > 1) for i in range(all_counts.shape[1])])]

    dem_counts = all_counts[:dem_user_len, :]
    rep_counts = all_counts[dem_user_len:, :]
    del wordcounts
    del all_counts
    gc.collect()

    dem_nonzero = set(dem_counts.nonzero()[0])
    rep_nonzero = set(rep_counts.nonzero()[0])
    # filter users who did not use words from vocab
    dem_counts = dem_counts[np.array([(i in dem_nonzero) for i in range(dem_counts.shape[0])]), :]
    rep_counts = rep_counts[np.array([(i in rep_nonzero) for i in range(rep_counts.shape[0])]), :]
    del dem_nonzero
    del rep_nonzero
    gc.collect()

    actual_val = calculate_polarization(dem_counts, rep_counts, token_partisanship_measure, leaveout)

    all_counts = sp.vstack([dem_counts, rep_counts])
    del dem_counts
    del rep_counts
    gc.collect()

    index = np.arange(all_counts.shape[0])
    RNG.shuffle(index)
    all_counts = all_counts[index, :]

    random_val = calculate_polarization(all_counts[:dem_user_len, :], all_counts[dem_user_len:, :],
                                        token_partisanship_measure, leaveout)
    print(actual_val, random_val, dem_user_len + rep_user_len)
    sys.stdout.flush()
    del all_counts
    gc.collect()

    return actual_val, random_val, dem_user_len + rep_user_len



def get_leaveout_emb_score(dem_counts, rep_counts, token_partisanship_measure='posterior',
                       leaveout=True, default_score=0.5, min_docs=10, max_docs=999):
    """
    Measure polarization.
    :param event: name of the event
    :param data: dataframe with 'text' and 'user_id'
    :param token_partisanship_measure: type of measure for calculating token partisanship based on user-token counts
    :param leaveout: whether to use leave-out estimation
    :param between_topic: whether the estimate is between topics or tokens
    :param default_score: default token partisanship score
    :return:
    """
    if dem_counts.sum() == 0 or rep_counts.sum() == 0:
        return 0.5, 0, 0
    from sklearn.metrics.pairwise import cosine_similarity
    sim_mat = cosine_similarity(dem_counts, rep_counts)
    # import ipdb; ipdb.set_trace()
    # print(sim_mat)
    return sim_mat.mean(), 0, 0


    # import gc
    #
    # dem_user_len = dem_counts.shape[0]
    # rep_user_len = rep_counts.shape[0]
    #
    # # return these values when there is not enough data to make predictions on
    # if dem_user_len < min_docs or rep_user_len < min_docs:
    #     return default_score, default_score, dem_user_len + rep_user_len
    #
    # if max_docs < dem_user_len:
    #     dem_counts = dem_counts[:dem_user_len]
    # if max_docs < rep_user_len:
    #     rep_counts = rep_counts[:rep_user_len]
    #
    # import random
    # RNG = random.Random()  # make everything reproducible
    # RNG.seed(42)
    # # make the prior neutral (i.e. make sure there are the same number of Rep and Dem users)
    # dem_user_len = dem_counts.shape[0]
    # rep_user_len = rep_counts.shape[0]
    # if dem_user_len > rep_user_len:
    #     dem_subset = np.array(RNG.sample(range(dem_user_len), rep_user_len))
    #     dem_counts = dem_counts[dem_subset, :]
    #     dem_user_len = dem_counts.shape[0]
    # elif rep_user_len > dem_user_len:
    #     rep_subset = np.array(RNG.sample(range(rep_user_len), dem_user_len))
    #     rep_counts = rep_counts[rep_subset, :]
    #     rep_user_len = rep_counts.shape[0]
    # assert (dem_user_len == rep_user_len)
    #
    # all_counts = sp.vstack([dem_counts, rep_counts])
    #
    # wordcounts = all_counts.nonzero()[1]
    #
    # # filter words used by fewer than 2 people
    # all_counts = all_counts[:, np.array([(np.count_nonzero(wordcounts == i) > 1) for i in range(all_counts.shape[1])])]
    #
    # dem_counts = all_counts[:dem_user_len, :]
    # rep_counts = all_counts[dem_user_len:, :]
    # del wordcounts
    # del all_counts
    # gc.collect()
    #
    # dem_nonzero = set(dem_counts.nonzero()[0])
    # rep_nonzero = set(rep_counts.nonzero()[0])
    # # filter users who did not use words from vocab
    # dem_counts = dem_counts[np.array([(i in dem_nonzero) for i in range(dem_counts.shape[0])]), :]
    # rep_counts = rep_counts[np.array([(i in rep_nonzero) for i in range(rep_counts.shape[0])]), :]
    # del dem_nonzero
    # del rep_nonzero
    # gc.collect()
    #
    # actual_val = calculate_polarization(dem_counts, rep_counts, token_partisanship_measure, leaveout)
    #
    # all_counts = sp.vstack([dem_counts, rep_counts])
    # del dem_counts
    # del rep_counts
    # gc.collect()
    #
    # index = np.arange(all_counts.shape[0])
    # RNG.shuffle(index)
    # all_counts = all_counts[index, :]
    #
    # random_val = calculate_polarization(all_counts[:dem_user_len, :], all_counts[dem_user_len:, :],
    #                                     token_partisanship_measure, leaveout)
    # print(actual_val, random_val, dem_user_len + rep_user_len)
    # sys.stdout.flush()
    # del all_counts
    # gc.collect()
    #
    # return actual_val, random_val, dem_user_len + rep_user_len
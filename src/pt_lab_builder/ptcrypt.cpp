// ptcrypt - decode / encode Cisco Packet Tracer files (.pkt, .pka) to / from their XML.
//
// The file format (Packet Tracer 7 and later), as publicly documented by the pka2xml project:
//   file = obfuscate1( TwofishEAX( obfuscate2( qCompress(xml) ) ) )
//   qCompress   = 4-byte big-endian uncompressed size + zlib stream
//   obfuscate2  : byte[i] ^= (len - i)
//   Twofish-EAX : key = 16 x 0x89, nonce = 16 x 0x10, 16-byte tag appended
//   obfuscate1  : out[i] = in[len-1-i] ^ (len - i*len)       (reverse + xor)
//
// Build: g++ -O2 -o ptcrypt ptcrypt.cpp -lcryptopp -lz
// Usage: ptcrypt decode FILE.pkt OUT.xml | ptcrypt encode IN.xml OUT.pkt
#include <cryptopp/eax.h>
#include <cryptopp/filters.h>
#include <cryptopp/twofish.h>
#include <zlib.h>

#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

using std::string;

static string read_file(const char *p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) throw std::runtime_error(string("cannot read ") + p);
    return string(std::istreambuf_iterator<char>(f), {});
}

static void write_file(const char *p, const string &s) {
    std::ofstream f(p, std::ios::binary);
    if (!f) throw std::runtime_error(string("cannot write ") + p);
    f.write(s.data(), (std::streamsize)s.size());
}

static const unsigned char KEY[16] = {0x89, 0x89, 0x89, 0x89, 0x89, 0x89, 0x89, 0x89,
                                      0x89, 0x89, 0x89, 0x89, 0x89, 0x89, 0x89, 0x89};
static const unsigned char IV[16] = {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10,
                                     0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10};

static string decode(const string &in) {
    const size_t n = in.size();
    string s1(n, '\0');
    for (size_t i = 0; i < n; i++)
        s1[i] = (char)((unsigned char)in[n - 1 - i] ^ (unsigned char)((n - i * n) & 0xff));

    string s2;
    CryptoPP::EAX<CryptoPP::Twofish>::Decryption d;
    d.SetKeyWithIV(KEY, sizeof KEY, IV, sizeof IV);
    CryptoPP::StringSource ss(s1, true,
        new CryptoPP::AuthenticatedDecryptionFilter(d, new CryptoPP::StringSink(s2)));

    const size_t m = s2.size();
    for (size_t i = 0; i < m; i++) s2[i] = (char)((unsigned char)s2[i] ^ (unsigned char)((m - i) & 0xff));

    if (m < 4) throw std::runtime_error("payload too short");
    const uLongf size = ((uLongf)(unsigned char)s2[0] << 24) | ((uLongf)(unsigned char)s2[1] << 16) |
                        ((uLongf)(unsigned char)s2[2] << 8) | (uLongf)(unsigned char)s2[3];
    string out(size, '\0');
    uLongf got = size;
    if (uncompress((Bytef *)out.data(), &got, (const Bytef *)s2.data() + 4, (uLong)(m - 4)) != Z_OK)
        throw std::runtime_error("zlib: cannot uncompress");
    out.resize(got);
    return out;
}

static string encode(const string &xml) {
    uLongf bound = compressBound((uLong)xml.size());
    string z(4 + bound, '\0');
    const uint32_t len = (uint32_t)xml.size();
    z[0] = (char)(len >> 24); z[1] = (char)(len >> 16); z[2] = (char)(len >> 8); z[3] = (char)len;
    if (compress2((Bytef *)z.data() + 4, &bound, (const Bytef *)xml.data(), (uLong)xml.size(), 9) != Z_OK)
        throw std::runtime_error("zlib: cannot compress");
    z.resize(4 + bound);

    const size_t m = z.size();
    for (size_t i = 0; i < m; i++) z[i] = (char)((unsigned char)z[i] ^ (unsigned char)((m - i) & 0xff));

    string enc;
    CryptoPP::EAX<CryptoPP::Twofish>::Encryption e;
    e.SetKeyWithIV(KEY, sizeof KEY, IV, sizeof IV);
    CryptoPP::StringSource ss(z, true,
        new CryptoPP::AuthenticatedEncryptionFilter(e, new CryptoPP::StringSink(enc)));

    const size_t n = enc.size();
    string out(n, '\0');
    for (size_t i = 0; i < n; i++)
        out[n - 1 - i] = (char)((unsigned char)enc[i] ^ (unsigned char)((n - i * n) & 0xff));
    return out;
}

int main(int argc, char **argv) {
    if (argc != 4) {
        std::cerr << "usage: ptcrypt decode FILE.pkt OUT.xml | ptcrypt encode IN.xml OUT.pkt\n";
        return 2;
    }
    try {
        const string mode = argv[1];
        if (mode == "decode") write_file(argv[3], decode(read_file(argv[2])));
        else if (mode == "encode") write_file(argv[3], encode(read_file(argv[2])));
        else throw std::runtime_error("mode must be decode or encode");
    } catch (const std::exception &e) {
        std::cerr << "ptcrypt: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
